"""Generic continuation/semantic-column associations; frozen layout parsing stays separate."""

import re
from dataclasses import replace
from datetime import date
from decimal import localcontext

import pymupdf

from app.source_layout import (
    Layout,
    Source,
    Span,
    columns,
    header_sources,
    number,
    source_date,
    spans_for,
    table_sources,
)
from app.source_layout import (
    inspect_layout as old_layout,
)


def merged_headings(spans):
    consumed, result = set(), []
    for i, item in enumerate(spans):
        if i in consumed:
            continue
        matches = [
            (j, other)
            for j, other in enumerate(spans)
            if other.page == item.page
            and j != i
            and j not in consumed
            and re.fullmatch(r"net|gross", item.text, re.I)
            and re.fullmatch(r"worth|amount|price", other.text, re.I)
            and abs(item.x0 - other.x0) < 3
            and 0 < other.y0 - item.y0 < 14
        ]
        if len(matches) == 1:
            j, other = matches[0]
            consumed.add(j)
            item = Span(
                item.page,
                min(item.x0, other.x0),
                item.y0,
                max(item.x1, other.x1),
                other.y1,
                item.text + " " + other.text,
            )
        result.append(item)
    return result


def wrapped_prices(spans):
    """Only join a one-digit fractional continuation in the same price cell/row."""
    replacements, removed, fragments = {}, set(), {}
    for anchor in spans:
        if not re.fullmatch(r"qty\.?|quantity|units", anchor.text, re.I):
            continue
        header = [s for s in spans if s.page == anchor.page and abs(s.cy - anchor.cy) < 8]
        cols = columns(header)
        prices = [i for i, (_, key) in enumerate(cols) if key == "unit_price"]
        if len(prices) != 1:
            continue
        index = prices[0]
        left = (cols[index - 1][0].cx + cols[index][0].cx) / 2 if index else 0
        right = (cols[index][0].cx + cols[index + 1][0].cx) / 2 if index + 1 < len(cols) else 100000
        bottom = min(
            (
                s.y0
                for s in spans
                if s.page == anchor.page
                and s.y0 > anchor.y1
                and re.match(r"sub\s*total|total|summary|notes|terms", s.text, re.I)
            ),
            default=100000,
        )
        for i, upper in enumerate(spans):
            if upper.page != anchor.page or not anchor.y1 < upper.y0 < bottom:
                continue
            if not left < upper.cx < right or not re.fullmatch(r"[\d,]+\.\d", upper.text):
                continue
            lower = [
                (j, s)
                for j, s in enumerate(spans)
                if j != i
                and s.page == upper.page
                and left < s.cx < right
                and re.fullmatch(r"\d", s.text)
                and 0 <= s.y0 - upper.y1 < 3
                and abs(s.x1 - upper.x1) < 3
                and s.y1 < bottom
            ]
            if len(lower) != 1:
                continue
            j, tail = lower[0]
            # A separately printed quantity on the continuation row is another item.
            if any(
                s.page == upper.page
                and abs(s.cy - tail.cy) < 4
                and abs(s.x1 - anchor.x1) < 5
                and number(s.text) is not None
                for s in spans
            ):
                continue
            merged = replace(upper, y1=tail.y1, text=upper.text + tail.text)
            replacements[i], fragments[merged.text] = merged, upper.text + "\n" + tail.text
            removed.add(j)
    return [replacements.get(i, s) for i, s in enumerate(spans) if i not in removed], fragments


def seller_sources(layout, spans):
    for label in spans:
        if not re.fullmatch(r"seller\s*:|supplier\s*:|from\s*:", label.text, re.I):
            continue
        buyers = [
            s
            for s in spans
            if s.page == label.page
            and abs(s.cy - label.cy) < 8
            and s.x0 > label.x0
            and re.match(r"client|buyer|customer|bill\s*to", s.text, re.I)
        ]
        boundary = min((s.x0 for s in buyers), default=100000)
        candidates = [
            s
            for s in spans
            if s.page == label.page
            and 0 <= s.y0 - label.y1 < 30
            and abs(s.x0 - label.x0) < 8
            and s.x1 < boundary
            and re.search(r"[A-Za-z]", s.text)
        ]
        if not candidates:
            continue
        nearest = min(s.y0 for s in candidates)
        names = [s for s in candidates if abs(s.y0 - nearest) < 2]
        if len(names) != 1:
            continue
        # Explicit sender/recipient geometry supersedes the legacy sender heuristic.
        layout.records["vendor_name"] = [
            Source(label.page, names[0].text, label.text + "\n" + names[0].text)
        ]
        ids = [
            s
            for s in spans
            if s.page == label.page
            and s.x0 >= label.x0 - 3
            and s.x1 < boundary
            and label.y1 < s.y0 < label.y1 + 100
            and re.match(r"GSTIN|Tax\s*Id", s.text, re.I)
        ]
        if ids:
            layout.records["vendor_tax_id"] = []
            for item in ids:
                match = re.search(r"\b\d{2}[A-Z0-9]{13}\b", item.text.upper())
                if match:
                    layout.add("vendor_tax_id", Source(item.page, match[0], item.text))


def issue_dates(layout, spans):
    for label in spans:
        if not re.fullmatch(r"date\s*of\s*issue\s*:", label.text, re.I):
            continue
        nearby = [
            s
            for s in spans
            if s.page == label.page and s.x0 > label.x1 and abs(s.cy - label.cy) < 7
        ]
        if not nearby:
            continue
        value = min(nearby, key=lambda s: s.x0)
        parsed = source_date(value.text)
        if parsed:
            layout.add("invoice_date", Source(label.page, parsed, label.text + " " + value.text))
        elif re.fullmatch(r"\d{2}/\d{2}/\d{4}", value.text):
            a, b, year = map(int, value.text.split("/"))
            for day, month in ((a, b), (b, a)):
                try:
                    candidate = date(year, month, day).isoformat()
                except ValueError:
                    continue
                layout.add(
                    "invoice_date", Source(label.page, candidate, label.text + " " + value.text)
                )


def summary_sources(layout, spans):
    for label in spans:
        if not re.fullmatch(r"summary", label.text, re.I):
            continue
        headers = [s for s in spans if s.page == label.page and 0 < s.y0 - label.y1 < 24]
        mapping = {
            "net worth": "subtotal_net",
            "net amount": "subtotal_net",
            "vat": "tax_total",
            "tax": "tax_total",
            "gross worth": "total_gross",
            "gross amount": "total_gross",
        }
        totals = [
            s
            for s in spans
            if s.page == label.page and s.y0 > label.y1 and re.fullmatch(r"total", s.text, re.I)
        ]
        if len(totals) != 1:
            continue
        stop = totals[0].y0
        headers = sorted(headers, key=lambda s: s.cx)
        for index, header in enumerate(headers):
            path = mapping.get(header.text.lower())
            if not path:
                continue
            left = (headers[index - 1].cx + header.cx) / 2 if index else 0
            right = (header.cx + headers[index + 1].cx) / 2 if index + 1 < len(headers) else 100000
            values = [
                s
                for s in spans
                if s.page == label.page
                and header.y1 < s.y0 < stop
                and left < s.cx < right
                and number(s.text) is not None
            ]
            if len(values) == 1:
                item = values[0]
                layout.add(
                    path, Source(item.page, str(number(item.text)), header.text + "\n" + item.text)
                )
            # Keep the final Total row independently; conflicting displays must
            # not disappear when the summary's intermediate row is correct.
            final_cells = sorted(
                (
                    s
                    for s in spans
                    if s.page == label.page
                    and s != totals[0]
                    and 0 <= s.y0 - totals[0].y0 < 18
                    and left < s.cx < right
                ),
                key=lambda s: (s.y0, s.x0),
            )
            final_values = [s for s in final_cells if number(s.text) is not None]
            if len(final_values) == 1:
                item = final_values[0]
                layout.add(
                    path,
                    Source(
                        item.page,
                        str(number(item.text)),
                        totals[0].text
                        + " "
                        + header.text
                        + " "
                        + " ".join(s.text for s in final_cells),
                    ),
                )


def inspect_layout(pdf, pages):
    old = old_layout(pdf, pages)
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        raw = spans_for(doc)
    if len(raw) > 15000:
        return old
    spans, fragments = wrapped_prices(merged_headings(raw))
    enhanced = fragments or any(
        re.fullmatch(r"Net Worth|Date of issue:|Seller:", s.text, re.I) for s in spans
    )
    if not enhanced:
        return old
    layout = Layout()
    # A Total followed by several amounts needs column headings to establish gross.
    safe_headers = [
        s
        for s in raw
        if not (
            re.fullmatch(r"total", s.text, re.I)
            and sum(
                other.page == s.page
                and other.x0 > s.x1
                and abs(other.cy - s.cy) < 8
                and number(other.text) is not None
                for other in raw
            )
            > 1
        )
    ]
    header_sources(layout, safe_headers)
    seller_sources(layout, raw)
    issue_dates(layout, raw)
    summary_sources(layout, spans)
    adapted = []
    for span in spans:
        text = span.text
        if re.fullmatch(r"net\s+(?:worth|amount)", text, re.I):
            text = "Amount"
        elif re.fullmatch(r"VAT\s*%", text, re.I):
            text = "Tax (%)"
        elif re.fullmatch(r"summary", text, re.I):
            text = "Notes"  # A table boundary, never persisted as source text.
        adapted.append(replace(span, text=text))
    with localcontext() as context:
        context.prec = 48
        table_sources(layout, adapted)
    # Keep independently printed gross cells alongside calculated gross. Conflicts
    # become multiple source values and cannot be rescued by arithmetic.
    gross_columns = [s for s in spans if re.fullmatch(r"gross\s+(?:worth|amount)", s.text, re.I)]
    for header in gross_columns:
        qty_headers = [
            s
            for s in spans
            if (
                s.page == header.page
                and abs(s.cy - header.cy) < 10
                and re.fullmatch(r"qty\.?|quantity|units", s.text, re.I)
            )
        ]
        if len(qty_headers) != 1:
            continue
        qty = qty_headers[0]
        cols = columns([s for s in spans if s.page == qty.page and abs(s.cy - qty.cy) < 8])
        index = next(i for i, (s, _) in enumerate(cols) if s == qty)
        left = (cols[index - 1][0].cx + qty.cx) / 2 if index else 0
        right = (qty.cx + cols[index + 1][0].cx) / 2 if index + 1 < len(cols) else 100000
        bottom = min(
            (
                s.y0
                for s in spans
                if s.page == qty.page
                and s.y0 > header.y1
                and re.match(r"summary|sub\s*total|total|notes|terms", s.text, re.I)
            ),
            default=100000,
        )
        rows = sorted(
            (
                s
                for s in spans
                if s.page == qty.page
                and header.y1 < s.y0 < bottom
                and left < s.cx < right
                and number(s.text) is not None
            ),
            key=lambda s: s.y0,
        )
        paths = sorted(
            (
                p
                for p, entries in layout.records.items()
                if p.endswith(".quantity") and entries[0].page == qty.page
            ),
            key=lambda p: int(p.split(".")[1]),
        )
        gross_index = next((i for i, (s, _) in enumerate(cols) if s == header), None)
        if gross_index is None:
            continue
        gross_left = (cols[gross_index - 1][0].cx + header.cx) / 2 if gross_index else 0
        gross_right = (
            (header.cx + cols[gross_index + 1][0].cx) / 2 if gross_index + 1 < len(cols) else 100000
        )
        for i, path in enumerate(paths):
            target = path.rsplit(".", 1)[0] + ".gross_amount"
            if len(rows) != len(paths) or number(rows[i].text) != layout.amount(path):
                layout.records.pop(target, None)
                continue
            row = rows[i]
            found = [
                s
                for s in spans
                if s.page == qty.page
                and abs(s.cy - row.cy) < 7
                and gross_left < s.cx < gross_right
                and number(s.text) is not None
            ]
            if len(found) == 1:
                cell = found[0]
                layout.add(target, Source(qty.page, str(number(cell.text)), cell.text))
            else:
                # An unresolved printed gross cell cannot be bypassed by deriving it.
                layout.records.pop(target, None)
    for path, entries in layout.records.items():
        if path.endswith(".unit_price"):
            layout.records[path] = [replace(s, text=fragments.get(s.text, s.text)) for s in entries]
    # Citations often pair a heading with a cell even though PDF reading order
    # lists all headings before the rows. The association is independently known.
    patterns = {
        "quantity": r"qty\.?|quantity|units",
        "unit_price": r"(?:net\s+|unit\s+)?price|rate",
        "description": r"(?:item\s+)?description|particulars",
    }
    for path, entries in list(layout.records.items()):
        key = path.rsplit(".", 1)[-1]
        if not path.startswith("lines.") or key not in patterns:
            continue
        updated = []
        for source in entries:
            headings = [
                s
                for s in spans
                if s.page == source.page and re.fullmatch(patterns[key], s.text, re.I)
            ]
            updated.append(
                replace(source, text=headings[0].text + "\n" + source.text)
                if len(headings) == 1
                else source
            )
        layout.records[path] = updated
    for source in old.records.get("currency", []):
        layout.add("currency", source)
    return layout
