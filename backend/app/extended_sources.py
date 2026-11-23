"""Independent associations for additive invoice fields; never consult master data."""

import re
from datetime import date

import pymupdf

from app.source_layout import Source, clean, columns, number, source_date, spans_for, tax_cell
from app.source_layout_v6 import merged_headings

HEADER_LABELS = {
    "due_date": r"due\s*date|payment\s*due(?:\s*date)?",
    "payment_terms": r"payment\s*terms|terms\s*(?:&|and)\s*conditions",
    "discount_amount": r"(?:total\s*)?discount(?:\s*amount)?",
    "discount_rate": r"discount\s*(?:rate|%)",
    "shipping_amount": (
        r"shipping(?:\s*(?:charges?|amount))?|freight(?:\s*charges?)?|delivery\s*charges?"
    ),
    "other_charges": r"other\s*charges?|additional\s*charges?",
    "rounding_adjustment": r"round(?:ing|\s*off)(?:\s*adjustment)?",
}


def parsed_number(value, *, signed=False):
    token = clean(value)
    if signed and token.startswith("-"):
        parsed = number(token[1:])
        return -parsed if parsed is not None else None
    return number(token)


def inspect_extra_sources(pdf, extraction):
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        spans = merged_headings(spans_for(document))
    records = {}
    declared_adjustments = set()

    def add(path, value, text, page):
        if value is not None:
            source = Source(page, str(value), text)
            if source not in records.setdefault(path, []):
                records[path].append(source)

    def adjacent(label):
        right = [
            s
            for s in spans
            if s.page == label.page
            and s.x0 >= label.x1 - 2
            and s != label
            and abs(s.cy - label.cy) < 7
        ]
        if right:
            return min(right, key=lambda s: s.x0)
        below = [
            s
            for s in spans
            if s.page == label.page and 0 <= s.y0 - label.y1 < 25 and abs(s.x0 - label.x0) < 15
        ]
        return min(below, key=lambda s: s.y0) if below else None

    for item in spans:
        is_table = any(
            s.page == item.page
            and abs(s.cy - item.cy) < 8
            and re.fullmatch(r"qty\.?|quantity|units", s.text, re.I)
            for s in spans
        )
        if not is_table:
            for path, pattern in HEADER_LABELS.items():
                if path == "shipping_amount" and re.match(r"shipping\s*address", item.text, re.I):
                    continue
                match = re.fullmatch(rf"(?:{pattern})\s*:?\s*(.*?)", item.text, re.I)
                if not match:
                    continue
                value = match[1]
                support = item.text
                if not value:
                    other = adjacent(item)
                    if other:
                        value = other.text
                        support += "\n" + other.text
                if path == "due_date":
                    printed = value
                    value = source_date(value)
                    if value is None and re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", printed):
                        a, b, year = map(int, re.split(r"[/-]", printed))
                        for day, month in ((a, b), (b, a)):
                            try:
                                add(path, date(year, month, day).isoformat(), support, item.page)
                            except ValueError:
                                pass
                elif path not in ("payment_terms",):
                    value = parsed_number(value, signed=path == "rounding_adjustment")
                    if path not in ("discount_amount", "discount_rate") or not re.search(
                        r"address", item.text, re.I
                    ):
                        declared_adjustments.add(path)
                add(path, value, support, item.page)
            component = re.fullmatch(
                r"(CGST|SGST|IGST|CESS)\s*(?:\(?\s*@?\s*(\d+(?:\.\d+)?)\s*%\s*\)?)?\s*:?\s*(.*)",
                item.text,
                re.I,
            )
            if component:
                kind, rate, tail = component.groups()
                kind = kind.lower()
                amount = parsed_number(tail) if tail else None
                support = item.text
                if amount is None:
                    other = adjacent(item)
                    if other and number(other.text) is not None:
                        amount = number(other.text)
                        support += "\n" + other.text
                add(kind + "_rate", rate, support, item.page)
                add(kind + "_amount", amount, support, item.page)

    # Explicit recipient regions, independent of supplier identity.
    regions = []
    for label in spans:
        match = re.fullmatch(
            r"(bill(?:ed)?\s*to|client|buyer|customer|ship\s*to|seller|supplier)\s*:?\s*(.*)",
            label.text,
            re.I,
        )
        if not match:
            continue
        role = (
            "ship"
            if match[1].lower().startswith("ship")
            else "vendor"
            if match[1].lower() in ("seller", "supplier")
            else "buyer"
        )
        peers = [
            s.x0
            for s in spans
            if s.page == label.page
            and s.x0 > label.x0 + 30
            and abs(s.cy - label.cy) < 8
            and re.match(r"client|buyer|seller|supplier|bill\s*to", s.text, re.I)
        ]
        edge = min(peers, default=100000)
        below = sorted(
            (
                s
                for s in spans
                if s.page == label.page
                and label.y1 < s.y0 < label.y1 + 130
                and abs(s.x0 - label.x0) < 18
                and s.x1 < edge
            ),
            key=lambda s: s.y0,
        )
        name = match[2] or (below[0].text if below else None)
        if not name:
            continue
        if not match[2]:
            below = below[1:]
        if role == "buyer":
            add("buyer_name", name, label.text + "\n" + name, label.page)
        address = []
        for row in below:
            if re.match(r"GSTIN|Tax\s*Id", row.text, re.I):
                if role == "buyer":
                    value = re.sub(r"^(?:GSTIN|Tax\s*Id)\s*:?\s*", "", row.text, flags=re.I)
                    add("buyer_tax_id", value, row.text, row.page)
                continue
            if re.match(r"PO\s*:", row.text, re.I):
                continue
            if re.match(
                r"invoice|due\s*date|date\s*of|place\s*of|#|items|notes|terms", row.text, re.I
            ):
                break
            address.append(row.text)
        add(
            "ship_to_address" if role == "ship" else role + "_address",
            "\n".join(([name] if role == "ship" else []) + address) if address else None,
            label.text + "\n" + "\n".join(address),
            label.page,
        )
        regions.append(role)
    if "vendor" not in regions and extraction.vendor_name:
        names = [
            s for s in spans if clean(s.text).casefold() == clean(extraction.vendor_name).casefold()
        ]
        if len(names) == 1:
            label = names[0]
            below = sorted(
                (
                    s
                    for s in spans
                    if s.page == label.page
                    and label.y1 < s.y0 < label.y1 + 100
                    and abs(s.x0 - label.x0) < 18
                ),
                key=lambda s: s.y0,
            )
            address = []
            for row in below:
                if re.match(r"GSTIN|tax\s*id|bill\s*to|invoice|#", row.text, re.I):
                    break
                address.append(row.text)
            if address:
                add("vendor_address", "\n".join(address), "\n".join(address), label.page)

    position = 0
    for anchor in spans:
        if not re.fullmatch(r"qty\.?|quantity|units", anchor.text, re.I):
            continue
        headers = [s for s in spans if s.page == anchor.page and abs(s.cy - anchor.cy) < 8]
        cols = columns(headers)
        qindex = next((i for i, (s, k) in enumerate(cols) if k == "quantity"), None)
        if qindex is None:
            continue
        bounds = [(cols[i][0].cx + cols[i + 1][0].cx) / 2 for i in range(len(cols) - 1)]
        bottom = min(
            (
                s.y0
                for s in spans
                if s.page == anchor.page
                and s.y0 > anchor.y1
                and re.match(r"summary|sub\s*total|total|notes|terms", s.text, re.I)
            ),
            default=100000,
        )
        start = max(s.y1 for s, _ in cols)
        cells = {i: [] for i in range(len(cols))}
        for span in spans:
            if span.page == anchor.page and start < span.cy < bottom:
                cells[sum(span.cx > b for b in bounds)].append(span)
        quantities = sorted(
            (s for s in cells[qindex] if number(s.text) is not None), key=lambda s: s.y0
        )
        for i, quantity in enumerate(quantities):
            position += 1
            low = start if i == 0 else (quantities[i - 1].cy + quantity.cy) / 2
            high = bottom if i + 1 == len(quantities) else (quantity.cy + quantities[i + 1].cy) / 2
            for index, (header, _) in enumerate(cols):
                values = sorted((s for s in cells[index] if low < s.cy < high), key=lambda s: s.y0)
                if not values:
                    continue
                label = header.text.lower()
                prefix = f"lines.{position}."
                support = header.text + "\n" + "\n".join(s.text for s in values)
                tax = re.search(r"cgst|sgst|igst|cess", label)
                if tax:
                    rate, amount = tax_cell(values, label)
                    add(prefix + tax[0] + "_rate", rate, support, anchor.page)
                    add(prefix + tax[0] + "_amount", amount, support, anchor.page)
                elif re.search(r"hsn|sac", label):
                    add(prefix + "hsn_sac", " ".join(s.text for s in values), support, anchor.page)
                elif "discount" in label:
                    value = " ".join(s.text for s in values)
                    key = "discount_rate" if "%" in label or "%" in value else "discount_amount"
                    declared_adjustments.add(prefix + key)
                    add(prefix + key, number(value), support, anchor.page)
    return records, declared_adjustments - set(records)
