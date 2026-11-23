"""Local PDF field association; no vendor masters, fixture hashes or model trust flags."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext

import pymupdf

from app.evidence_legacy import labelled_records
from app.finance_contracts import money


def clean(value):
    return " ".join(str(value).replace("\u00a0", " ").split())


def number(value):
    value = clean(value)
    if len(value) > 64:
        return None
    value = re.sub(r"^(?:INR|Rs\.?|₹|USD|\$)\s*", "", value, flags=re.I)
    value = re.sub(r"\s*(?:%|INR)$", "", value, flags=re.I)
    if not re.fullmatch(
        r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})*,[0-9]{3})(?:\.[0-9]+)?",
        value,
    ):
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def source_date(value):
    value = clean(value)
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    # Numeric day/month order is not guessed when both interpretations are possible.
    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", value)
    if match:
        first, second, year = map(int, match.groups())
        if first > 12 >= second or first == second:
            try:
                return datetime(year, second, first).date().isoformat()
            except ValueError:
                pass
        elif second > 12 >= first:
            try:
                return datetime(year, first, second).date().isoformat()
            except ValueError:
                pass
    return None


@dataclass(frozen=True)
class Span:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True)
class Source:
    page: int
    value: str
    text: str
    derived: bool = False
    calculation: str | None = None
    pages: tuple[int, ...] = ()


HEADER_PATTERNS = {
    "invoice_number": r"invoice\s*(?:number|no\.?|#)",
    "invoice_date": r"invoice\s*date|date\s*of\s*invoice",
    "po_reference": (
        r"p\.?\s*o\.?(?![A-Za-z])\s*(?:number|no\.?|reference|#)?|"
        r"purchase\s*order(?:\s*(?:number|no\.?|reference|#))?"
    ),
    "subtotal_net": (
        r"sub\s*total(?:\s*net)?|net\s*(?:sub\s*total|amount)|"
        r"taxable\s*(?:value|amount)"
    ),
    "tax_total": r"(?:total\s*(?:tax|gst)|(?:tax|gst)\s*(?:total|amount))",
    "total_gross": (
        r"grand\s*total|invoice\s*total|total\s*(?:gross|amount|payable)|"
        r"amount\s*due|balance\s*due|total"
    ),
    "currency": r"currency",
    "tax_mode": r"tax\s*mode",
    "bank_account_last4": (
        r"bank\s*account\s*last\s*4|bank\s*account\s*last\s*four|"
        r"(?:bank\s*)?(?:account|a/c)\s*(?:no\.?|number|#)"
    ),
}


@dataclass
class Layout:
    records: dict[str, list[Source]] = field(default_factory=dict)
    tables: bool = False

    def add(self, path, source):
        entries = self.records.setdefault(path, [])
        if source not in entries:
            entries.append(source)

    def one(self, path):
        entries = self.records.get(path, [])
        numeric = path.rsplit(".", 1)[-1] in {
            "subtotal_net",
            "tax_total",
            "total_gross",
            "quantity",
            "unit_price",
            "tax_rate",
            "net_amount",
            "tax_amount",
            "gross_amount",
        }
        values = {number(item.value) if numeric else item.value for item in entries}
        return entries[0] if len(values) == 1 else None

    def amount(self, path):
        source = self.one(path)
        return number(source.value) if source else None


def spans_for(doc):
    return [
        Span(page_no, *line["bbox"], clean("".join(s["text"] for s in line["spans"])))
        for page_no, page in enumerate(doc, 1)
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        if clean("".join(s["text"] for s in line["spans"]))
    ]


def header_sources(layout, spans):
    for item in spans:
        for path, pattern in HEADER_PATTERNS.items():
            match = re.fullmatch(rf"\s*(?:{pattern})\s*[:#]?\s*(.*?)\s*", item.text, re.I)
            if not match:
                continue
            value = match.group(1)
            context = item.text
            if not value:
                # Prefer a label/value pair on the same geometric row. Never take
                # an arbitrary occurrence of the same number elsewhere on the page.
                adjacent = [
                    other
                    for other in spans
                    if other.page == item.page
                    and other.x0 >= item.x1 - 2
                    and abs(other.cy - item.cy) < 7
                    and other is not item
                ]
                if adjacent:
                    other = min(adjacent, key=lambda s: s.x0)
                    value, context = other.text, item.text + " " + other.text
                else:
                    below = [
                        s
                        for s in spans
                        if s.page == item.page
                        and 0 < s.y0 - item.y1 < 24
                        and abs(s.x0 - item.x0) < 16
                    ]
                    if below:
                        other = min(below, key=lambda s: s.y0)
                        value, context = other.text, item.text + "\n" + other.text
            if not value:
                continue
            if path in ("subtotal_net", "tax_total", "total_gross"):
                parsed = number(value)
                if parsed is None:
                    continue
                value = str(parsed)
            elif path == "invoice_date":
                value = source_date(value)
                if value is None:
                    continue
            elif path == "po_reference":
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ./_-]{0,99}", value):
                    continue
            elif path == "bank_account_last4":
                digits = re.sub(r"[^0-9]", "", value)
                if len(digits) < 4:
                    continue
                value = digits[-4:]
            layout.add(path, Source(item.page, value, context))

    buyers = [
        s
        for s in spans
        if re.match(
            r"(?:bill(?:ed)?\s*to|sold\s*to|invoiced\s*to|buyer|customer|ship\s*to)\b", s.text, re.I
        )
    ]
    for item in spans:
        # Supplier identity is drawn from the sender region, not the Bill To GSTIN.
        buyer_rows = [s.y0 for s in buyers if s.page == item.page and s.x0 < item.x1 + 10]
        if buyer_rows and item.y0 >= min(buyer_rows) - 2:
            continue
        if re.search(r"\b(?:GSTIN|GST\s*(?:No\.?|Number)|tax\s*id)\b", item.text, re.I):
            match = re.search(r"\b[0-9]{2}[A-Z0-9]{13}\b", item.text.upper())
            if match:
                layout.add("vendor_tax_id", Source(item.page, match.group(), item.text))
        elif not re.search(
            r"invoice|date|currency|\bGST\b|\bPO\b|total|https?://", item.text, re.I
        ):
            if re.search(r"[A-Za-z]", item.text):
                if not any(s.page == item.page for s in buyers) and not re.match(
                    r"(?:supplier|seller|from|vendor\s*name)\s*:", item.text, re.I
                ):
                    # With no sender/recipient boundary, a convenient company
                    # name somewhere on the page is insufficient identity proof.
                    continue
                value = re.sub(
                    r"^(?:supplier|seller|from|vendor\s*name)\s*:\s*", "", item.text, flags=re.I
                )
                layout.add("vendor_name", Source(item.page, value, item.text))

    components = []
    for item in spans:
        match = re.fullmatch(
            r"(?:[ICSU]?GST|tax|cess)\s*\(?\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*\)?\s*:?", item.text, re.I
        )
        if match:
            adjacent = [
                s
                for s in spans
                if s.page == item.page
                and s.x0 >= item.x1
                and abs(s.cy - item.cy) < 7
                and number(s.text) is not None
            ]
            if adjacent:
                amount = min(adjacent, key=lambda s: s.x0)
                components.append((item, Decimal(match.group(1)), number(amount.text), amount))
    if components:
        if not any(re.search(r"gst|tax", label.text, re.I) for label, _, _, _ in components):
            return
        rate = sum((r for _, r, _, _ in components), Decimal("0"))
        tax = sum((a for _, _, a, _ in components), Decimal("0.00"))
        context = "\n".join(label.text + " " + amount.text for label, _, _, amount in components)
        pages = tuple(sorted({label.page for label, _, _, _ in components}))
        layout.add(
            "_header_tax_rate",
            Source(
                pages[0], str(rate), context, True, "Sum of printed footer tax percentages.", pages
            ),
        )
        if "tax_total" not in layout.records:
            layout.add(
                "tax_total",
                Source(
                    pages[0],
                    str(tax),
                    context,
                    True,
                    "Sum of printed footer tax-component amounts.",
                    pages,
                ),
            )


def columns(header):
    result = []
    for span in header:
        label = span.text.lower().strip()
        key = None
        if re.fullmatch(r"#|s\.?\s*no\.?|line(?:\s*no\.?)?", label):
            key = "number"
        elif re.fullmatch(r"sku|item\s*code|product\s*code", label):
            key = "sku"
        elif re.fullmatch(r"po\s*line(?:\s*no\.?)?", label):
            key = "po_line_no"
        elif (
            re.search(r"description|particular|item(?:\s*name)?|product|service", label)
            and "price" not in label
        ):
            key = "description"
        elif re.fullmatch(r"qty\.?|quantity|units", label):
            key = "quantity"
        elif re.search(r"rate|unit\s*price|price", label) and not re.search(r"gst|tax|cess", label):
            key = "unit_price"
        elif re.search(r"(?:[ICSU]?GST|cess|tax)", label, re.I):
            key = "tax:" + label
        elif re.fullmatch(r"(?:net\s*|gross\s*|line\s*)?(?:amount|total)(?:\s*\([^)]*\))?", label):
            key = "amount"
        # Keep ignored columns (HSN/SAC, unit) as geometric boundaries too.
        result.append((span, key))
    return sorted(result, key=lambda pair: pair[0].cx)


def tax_cell(values, label):
    """A tax cell can print rate + amount on two lines, or an explicit percent."""
    numeric = [(span, number(span.text)) for span in values if number(span.text) is not None]
    percent = [(span, value) for span, value in numeric if "%" in span.text]
    if percent:
        rates = {value for _, value in percent}
        if len(rates) == 1:
            rate = next(iter(rates))
            amounts = [(s, v) for s, v in numeric if "%" not in s.text]
            return rate, amounts[0][1] if len(amounts) == 1 else None
    if "%" in label and len(numeric) == 1:
        return numeric[0][1], None
    if len(numeric) == 2:
        # Zoho-style stacked cells print amount above the percentage.
        upper, lower = sorted(numeric, key=lambda pair: pair[0].y0)
        if 0 <= lower[1] <= 100 and lower[0].y0 > upper[0].y0 + 2:
            return lower[1], upper[1]
    if len(numeric) == 1 and numeric[0][1] == 0:
        return Decimal("0"), Decimal("0")
    return None, None


def table_sources(layout, spans):
    rows = []
    seen = set()
    for anchor in spans:
        if not re.fullmatch(r"qty\.?|quantity|units", anchor.text, re.I):
            continue
        key = (anchor.page, round(anchor.cy / 8))
        if key in seen:
            continue
        header = [s for s in spans if s.page == anchor.page and abs(s.cy - anchor.cy) < 8]
        cols = columns(header)
        keys = {key for _, key in cols}
        if not {"description", "quantity", "unit_price", "amount"} <= keys:
            continue
        seen.add(key)
        layout.tables = True
        bottom = min(
            (
                s.y0
                for s in spans
                if s.page == anchor.page
                and s.y0 > anchor.y1
                and re.match(r"sub\s*total|total|notes|terms", s.text, re.I)
            ),
            default=100000,
        )
        start = max(s.y1 for s, _ in cols)
        bounds = [(cols[i][0].cx + cols[i + 1][0].cx) / 2 for i in range(len(cols) - 1)]
        cells = {key: [] for _, key in cols if key}
        for span in spans:
            if span.page != anchor.page or not start < span.cy < bottom:
                continue
            index = sum(span.cx > bound for bound in bounds)
            key = cols[index][1]
            if key:
                cells[key].append(span)
        quantities = sorted(
            (s for s in cells["quantity"] if number(s.text) is not None), key=lambda s: s.y0
        )
        for index, quantity in enumerate(quantities):
            low = start if index == 0 else (quantities[index - 1].cy + quantity.cy) / 2
            high = (
                bottom
                if index + 1 == len(quantities)
                else (quantity.cy + quantities[index + 1].cy) / 2
            )
            row = {
                key: sorted((s for s in value if low < s.cy < high), key=lambda s: (s.y0, s.x0))
                for key, value in cells.items()
            }
            if len(row["unit_price"]) != 1 or len(row["amount"]) != 1 or not row["description"]:
                continue
            price, amount = number(row["unit_price"][0].text), number(row["amount"][0].text)
            if price is None or amount is None:
                continue
            components = [
                tax_cell(value, name) for name, value in row.items() if name.startswith("tax:")
            ]
            if not any(name.startswith("tax:") and "cess" not in name for name in row):
                components = []
            rate = (
                sum((r for r, _ in components), Decimal("0"))
                if components and all(r is not None for r, _ in components)
                else None
            )
            tax = (
                sum((a for _, a in components), Decimal("0.00"))
                if components and all(a is not None for _, a in components)
                else None
            )
            rows.append(
                dict(
                    page=anchor.page,
                    cells=row,
                    quantity=number(quantity.text),
                    price=price,
                    amount=amount,
                    rate=rate,
                    tax=tax,
                    components=components,
                    explicit_net=any(
                        re.search(r"\bnet\b", s.text, re.I) for s, k in cols if k == "unit_price"
                    ),
                )
            )
    if not rows:
        return
    if len(rows) == 1 and rows[0]["rate"] is None and layout.one("_header_tax_rate"):
        rows[0]["rate"] = layout.amount("_header_tax_rate")
        rows[0]["tax"] = layout.amount("tax_total")
        rows[0]["components"] = [(rows[0]["rate"], rows[0]["tax"])]
    subtotal, total = layout.amount("subtotal_net"), layout.amount("total_gross")
    line_sum = sum((row["amount"] for row in rows), Decimal("0"))
    for index, row in enumerate(rows, 1):
        path = f"lines.{index}."
        text = "\n".join(s.text for values in row["cells"].values() for s in values)
        page = row["page"]
        for key in ("description", "quantity", "unit_price", "sku", "po_line_no"):
            source = row["cells"].get(key, [])
            if source:
                value = " ".join(s.text for s in source)
                if key in ("quantity", "unit_price"):
                    value = str(number(value))
                layout.add(path + key, Source(page, value, "\n".join(s.text for s in source)))
        rate, tax = row["rate"], row["tax"]
        basis = None
        if (
            row["explicit_net"]
            or subtotal is not None
            and line_sum == subtotal
            and row["quantity"] * row["price"] == row["amount"]
        ):
            basis = "NET"
        elif (
            total is not None
            and line_sum == total
            and subtotal != total
            and row["quantity"] * row["price"] == row["amount"]
        ):
            basis = "GROSS"
        if rate is not None:
            layout.add(
                path + "tax_rate",
                Source(
                    page,
                    str(rate),
                    text,
                    True,
                    "Combined tax rate = "
                    + " + ".join(str(r) for r, _ in row.get("components", [(rate, tax)]))
                    + f" = {rate}%.",
                ),
            )
        if basis is None or rate is None:
            continue
        with localcontext() as context:
            context.prec = 48
            net = row["amount"] if basis == "NET" else money(row["amount"] / (1 + rate / 100))
            tax = money(net * rate / 100) if tax is None else tax
            gross = net + tax
        # Source arithmetic remains observable; verifier later rejects inconsistencies.
        for key, value, calculation in (
            (
                "price_basis",
                basis,
                "Table amounts reconcile to the printed subtotal/gross; "
                "tax components are explicit.",
            ),
            (
                "net_amount",
                str(net),
                f"Net line amount = {net}; source table price basis is {basis}.",
            ),
            (
                "tax_amount",
                str(tax),
                f"Line tax = {tax}; checked against net {net} × combined rate {rate}%.",
            ),
            ("gross_amount", str(gross), f"Line gross = {net} + {tax} = {gross}."),
        ):
            layout.add(path + key, Source(page, value, text, True, calculation))
    taxes = [layout.amount(f"lines.{i}.tax_amount") for i in range(1, len(rows) + 1)]
    if all(v is not None for v in taxes) and "tax_total" not in layout.records:
        layout.add(
            "tax_total",
            Source(
                rows[0]["page"],
                str(sum(taxes, Decimal("0.00"))),
                "\n".join(
                    s.text
                    for s in spans
                    if s.page == rows[0]["page"] and re.search(r"gst|cess|tax", s.text, re.I)
                ),
                True,
                "Total tax = "
                + " + ".join(str(t) for t in taxes)
                + f" = {sum(taxes, Decimal('0.00'))}.",
                tuple(sorted({row["page"] for row in rows})),
            ),
        )
    bases = [layout.one(f"lines.{i}.price_basis") for i in range(1, len(rows) + 1)]
    if all(b and b.value == "NET" for b in bases):
        layout.add(
            "tax_mode",
            Source(
                rows[0]["page"],
                "EXCLUSIVE",
                "Table subtotal and separately evidenced tax components",
                True,
                "All evidenced unit prices are net of the explicit tax components.",
            ),
        )
    elif all(b and b.value == "GROSS" for b in bases):
        layout.add(
            "tax_mode",
            Source(
                rows[0]["page"],
                "INCLUSIVE",
                "Table gross amounts and separately evidenced tax components",
                True,
                "All evidenced unit prices include the explicit tax components.",
            ),
        )


def derive_header_tax_mode(layout):
    """Derive exclusive tax from independently associated footer values."""
    if layout.records.get("tax_mode"):
        return

    subtotal_source = layout.one("subtotal_net")
    total_source = layout.one("total_gross")
    component_source = layout.one("_header_tax_rate")
    tax_source = layout.one("tax_total")

    if not all((
        subtotal_source,
        total_source,
        component_source,
        tax_source,
    )):
        return

    subtotal = layout.amount("subtotal_net")
    total = layout.amount("total_gross")
    tax = layout.amount("tax_total")

    if any(v is None for v in (subtotal, total, tax)):
        return

    # Require an independently identified net subtotal,
    # gross total and separately printed tax components.
    if subtotal_source.derived or total_source.derived:
        return

    if not all((
        "subtotal" in subtotal_source.text.lower().replace(" ", ""),
        any(word in total_source.text.lower()
            for word in ("total", "payable", "due")),
        any(word in component_source.text.lower()
            for word in ("cgst", "sgst", "igst", "gst")),
    )):
        return

    if subtotal <= 0 or tax <= 0:
        return

    if subtotal + tax != total:
        return

    pages = tuple(sorted(set(
        (subtotal_source.page, total_source.page)
        + (component_source.pages or (component_source.page,))
    )))

    layout.add(
        "tax_mode",
        Source(
            page=pages[0],
            value="EXCLUSIVE",
            text=(
                subtotal_source.text + "\n"
                + component_source.text + "\n"
                + total_source.text
            ),
            derived=True,
            calculation=(
                f"Net subtotal {subtotal} + separately identified "
                f"GST {tax} = gross total {total}"
            ),
            pages=pages,
        ),
    )


def inspect_layout(pdf, pages):
    layout = Layout()
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        spans = spans_for(document)
    if len(spans) > 15000:
        return layout
    header_sources(layout, spans)
    with localcontext() as context:
        context.prec = 48
        table_sources(layout, spans)
    # Original labelled fixtures remain supported; they are never used as templates.
    for path, entries in labelled_records(pages).items():
        for page, row, value in entries:
            layout.add(path, Source(page, value, row))
    for page, text in enumerate(pages, 1):
        codes = set(re.findall(r"\b(?:INR|USD|EUR|GBP|AED)\b", text))
        if "₹" in text:
            codes.add("INR")
        if (
            not codes
            and re.search(r"\bRs\.?\s*[\d,]", text)
            and re.search(r"\bIndia\b", text, re.I)
            and re.search(r"\b(?:IGST|CGST|SGST)\b", text)
        ):
            layout.add(
                "currency",
                Source(
                    page,
                    "INR",
                    "Rs. + India + printed Indian GST component headings",
                    True,
                    "Rupee notation corroborated by printed India/GST context; "
                    "no currency conversion.",
                ),
            )
        elif len(codes) == 1 and "currency" not in layout.records:
            code = next(iter(codes))
            layout.add("currency", Source(page, code, code if code in text else "₹"))
        elif len(codes) > 1:
            for code in codes:
                layout.add("currency", Source(page, code, code))
    derive_header_tax_mode(layout)
    return layout
