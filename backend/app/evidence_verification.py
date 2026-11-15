"""Conservative local field association and arithmetic checks; model evidence is untrusted."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

from pydantic import ValidationError

from app.extraction_schema import InvoiceExtractionV1
from app.finance_contracts import Evidence, FinancialDocument, money
from app.finance_rules import critical_check
from app.pdf_input import inspect_pdf

ALIASES = {
    "vendor name": "vendor_name",
    "supplier": "vendor_name",
    "vendor tax id": "vendor_tax_id",
    "gstin": "vendor_tax_id",
    "invoice number": "invoice_number",
    "invoice no": "invoice_number",
    "invoice date": "invoice_date",
    "po reference": "po_reference",
    "currency": "currency",
    "subtotal net": "subtotal_net",
    "net subtotal": "subtotal_net",
    "tax total": "tax_total",
    "total gross": "total_gross",
    "amount due": "total_gross",
    "tax mode": "tax_mode",
    "bank account last4": "bank_account_last4",
    "sku": "sku",
    "description": "description",
    "quantity": "quantity",
    "unit price": "unit_price",
    "price basis": "price_basis",
    "tax rate": "tax_rate",
    "net amount": "net_amount",
    "tax amount": "tax_amount",
    "gross amount": "gross_amount",
    "po line no": "po_line_no",
}
NUMERIC = {
    "subtotal_net",
    "tax_total",
    "total_gross",
    "quantity",
    "unit_price",
    "tax_rate",
    "net_amount",
    "tax_amount",
    "gross_amount",
    "po_line_no",
}
VERIFIER_VERSION = "labelled-fields-3"


def labelled_records(pages):
    records = {}
    for page, text in enumerate(pages, 1):
        for row in text.splitlines():
            match = re.fullmatch(r"\s*(.*?)\s*:\s*(\S.*?)\s*", row)
            if not match:
                continue
            label, value = match.groups()
            line = re.fullmatch(r"Line ([1-9][0-9]*) (.+)", label, re.I)
            name = ALIASES.get((line.group(2) if line else label).lower())
            if name:
                path = f"lines.{line.group(1)}.{name}" if line else name
                records.setdefault(path, []).append((page, row, value))
    return records


def value_matches(field, value, source):
    if value is None:
        return False
    if field.rsplit(".", 1)[-1] in NUMERIC:
        if not re.fullmatch(
            r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})*,[0-9]{3})(?:\.[0-9]+)?",
            source,
        ):
            return False
        try:
            return Decimal(str(value)) == Decimal(source.replace(",", ""))
        except InvalidOperation:
            return False
    return str(value) == source


@dataclass(frozen=True)
class Verification:
    document: FinancialDocument | None
    findings: tuple[str, ...]
    provenance: tuple[dict, ...]

    @property
    def needs_review(self):
        return bool(self.findings)


def verify(extraction: InvoiceExtractionV1, pdf: bytes) -> Verification:
    local = inspect_pdf(pdf)
    records = labelled_records(local.pages)
    data = extraction.model_dump()
    data["lines"] = data.pop("line_items")
    supplied = data.pop("evidence")
    fields = {k: v for k, v in data.items() if k != "lines" and v is not None}
    findings, provenance, evidence = [], [], []
    for line in data["lines"]:
        if (
            line["line_no"] is None
            or line["description"] is None
            or line["price_basis"] not in ("NET", "GROSS")
        ):
            findings.append("CRITICAL_LINE_FIELD_MISSING")
            continue
        fields.update(
            {
                f"lines.{line['line_no']}.{k}": v
                for k, v in line.items()
                if k != "line_no" and v is not None
            }
        )
    for path, value in fields.items():
        candidates = records.get(path, [])
        grounded = None
        # Repeated/contradictory labels are ambiguous even if one equals the model output.
        if len(candidates) == 1:
            page, row, source = candidates[0]
            for snippet in supplied:
                raw = snippet["raw_text"]
                masked_bank = (
                    path == "bank_account_last4"
                    and re.fullmatch(r"[0-9]{4}", source)
                    and re.sub(r"[*Xx]+(?=[0-9]{4}\b)", "", raw) in row
                )
                if (
                    snippet["field"] == path
                    and snippet["page"] == page
                    and raw.strip()
                    and (raw in row or masked_bank)
                    and value_matches(path, value, source)
                ):
                    grounded = (page, raw)
                    break
        provenance.append(
            {
                "field": path,
                "grounded": grounded is not None,
                "method": "TEXT" if grounded else "VISION_OR_UNGROUNDED",
                "page": grounded[0] if grounded else None,
            }
        )
        if grounded:
            evidence.append(
                Evidence(
                    field=path, page=grounded[0], raw_text=grounded[1], method="TEXT", verified=True
                )
            )
    # Optional means absent from the source, not permission for the model to drop
    # a printed identifier and bypass bank, identity, PO or line matching checks.
    if any(path not in fields for path in records):
        findings.append("PRINTED_FIELD_OMITTED")
    if not any(p.strip() for p in local.pages):
        findings.append("SCANNED_EVIDENCE_REQUIRES_REVIEW")
    if data["currency"] != "INR":
        findings.append("UNSUPPORTED_OR_MISSING_CURRENCY")
    if data["tax_mode"] is None:
        data["tax_mode"] = "UNKNOWN"
    data["evidence"] = evidence
    try:
        # Explicit conversion, no computed defaults. Values remain null when not printed.
        if data["invoice_date"] is not None:
            date.fromisoformat(data["invoice_date"])
        document = FinancialDocument.model_validate(data)
    except (ValidationError, ValueError):
        return Verification(
            None, tuple(sorted(set(findings + ["FINANCIAL_CONTRACT_INVALID"]))), tuple(provenance)
        )
    missing = critical_check(document)
    if missing:
        findings.append(missing.code)
    with localcontext() as context:
        context.prec = 48
        if all(
            v is not None for v in (document.subtotal_net, document.tax_total, document.total_gross)
        ):
            if document.subtotal_net + document.tax_total != document.total_gross:
                findings.append("ARITHMETIC_MISMATCH")
        sums = [Decimal("0"), Decimal("0"), Decimal("0")]
        complete = bool(document.lines)
        for line in document.lines:
            values = (
                line.quantity,
                line.unit_price,
                line.tax_rate,
                line.net_amount,
                line.tax_amount,
                line.gross_amount,
            )
            if any(v is None for v in values):
                complete = False
                continue
            unit = (
                line.unit_price
                if line.price_basis == "NET"
                else line.unit_price / (1 + line.tax_rate / 100)
            )
            if (
                line.net_amount != money(line.quantity * unit)
                or line.tax_amount != money(line.net_amount * line.tax_rate / 100)
                or line.gross_amount != line.net_amount + line.tax_amount
            ):
                findings.append("LINE_ARITHMETIC_MISMATCH")
            for i, value in enumerate((line.net_amount, line.tax_amount, line.gross_amount)):
                sums[i] += value
        if complete and tuple(sums) != (
            document.subtotal_net,
            document.tax_total,
            document.total_gross,
        ):
            findings.append("HEADER_LINE_SUM_MISMATCH")
    if findings:
        # A caller cannot bypass the verification report by passing its diagnostic
        # document straight to the financial service: unresolved evidence is untrusted.
        document = document.model_copy(
            update={
                "evidence": tuple(
                    item.model_copy(update={"verified": False}) for item in document.evidence
                )
            }
        )
    return Verification(document, tuple(sorted(set(findings))), tuple(provenance))
