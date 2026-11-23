"""Independently ground ordinary invoice layouts; preserve frozen legacy verification."""

import re
from decimal import Decimal, localcontext

from pydantic import ValidationError

from app.evidence_legacy import (  # Re-export helpers used by labelled fixture tooling.
    ALIASES,  # noqa: F401
    NUMERIC,
    Verification,
    labelled_records,
    value_matches,  # noqa: F401
)
from app.evidence_legacy import verify as legacy_verify
from app.extraction_schema import InvoiceExtractionV1
from app.finance_contracts import Evidence, FinancialDocument, money, normalized_name
from app.finance_rules import critical_check
from app.pdf_input import inspect_pdf
from app.source_layout import clean, inspect_layout, number

VERIFIER_VERSION = "layout-grounding-4"
LEGACY_VERIFIER_VERSION = "labelled-fields-3"
SUPPORTED_VERIFIERS = (LEGACY_VERIFIER_VERSION, VERIFIER_VERSION)
DERIVABLE = {
    "currency",
    "tax_total",
    "tax_mode",
    "price_basis",
    "tax_rate",
    "net_amount",
    "tax_amount",
    "gross_amount",
}


def matches(path, value, source):
    if value is None:
        return False
    name = path.rsplit(".", 1)[-1]
    if name in NUMERIC:
        return number(value) is not None and number(value) == number(source.value)
    if path == "vendor_name" or name == "description":
        return normalized_name(value) == normalized_name(source.value)
    return clean(value) == clean(source.value)


def verify(extraction: InvoiceExtractionV1, pdf: bytes, *, version=VERIFIER_VERSION):
    if version == LEGACY_VERIFIER_VERSION:
        return legacy_verify(extraction, pdf)
    if version != VERIFIER_VERSION:
        raise ValueError("Unsupported frozen evidence verifier")
    local = inspect_pdf(pdf)
    layout = inspect_layout(pdf, local.pages)
    labels = labelled_records(local.pages)
    if not layout.tables and {"vendor_name", "invoice_number", "total_gross"} <= labels.keys():
        return legacy_verify(extraction, pdf)
    data = extraction.model_dump()
    supplied = data.pop("evidence")
    data["lines"] = data.pop("line_items")
    # These indices identify extracted rows, not asserted printed numbering.
    line_numbers = [line["line_no"] for line in data["lines"]]
    aliases = {
        str(line["line_no"]): str(index)
        for index, line in enumerate(data["lines"], 1)
        if line["line_no"] is not None and line_numbers.count(line["line_no"]) == 1
    }
    supplied = [
        dict(
            snippet,
            field=".".join(
                [
                    "lines",
                    aliases.get(snippet["field"].split(".")[1], snippet["field"].split(".")[1]),
                    snippet["field"].split(".")[2],
                ]
            ),
        )
        if re.fullmatch(r"lines\.[1-9][0-9]*\.[a-z_]+", snippet["field"])
        else snippet
        for snippet in supplied
    ]
    for index, line in enumerate(data["lines"], 1):
        line["line_no"] = index
    fields = {key: value for key, value in data.items() if key != "lines"}
    for index, line in enumerate(data["lines"], 1):
        fields.update(
            {f"lines.{index}.{key}": value for key, value in line.items() if key != "line_no"}
        )
    evidence, provenance, findings = [], [], []
    for path, value in fields.items():
        candidates = layout.records.get(path, [])
        consistent = (
            path == "vendor_name"
            or len(
                {
                    number(s.value) if path.rsplit(".", 1)[-1] in NUMERIC else clean(s.value)
                    for s in candidates
                }
            )
            == 1
        )
        source = layout.one(path)
        recovered_printed = bool(
            value is None and path == "subtotal_net" and source and not source.derived
        )
        if (
            (
                value is None
                or value == "UNKNOWN"
                or path == "currency"
                and str(value).lower() in ("rs", "rs.", "₹", "indian rupee")
            )
            and source
            and source.derived
            and path.rsplit(".", 1)[-1] in DERIVABLE
        ):
            value = source.value
            if path.startswith("lines."):
                _, index, key = path.split(".")
                data["lines"][int(index) - 1][key] = value
            else:
                data[path] = value
        elif recovered_printed:
            value = source.value
            data[path] = value
        grounded, used = None, None
        if consistent and value is not None:
            for source in candidates:
                if not matches(path, value, source):
                    continue
                if source.derived or recovered_printed:
                    grounded, used = source, source.text
                    break
                for snippet in supplied:
                    raw = clean(snippet["raw_text"])
                    masked = path == "bank_account_last4" and re.sub(
                        r"[*Xx]+(?=[0-9]{4}\b)", "", raw
                    ) in clean(source.text)
                    if (
                        snippet["field"] == path
                        and snippet["page"] == source.page
                        and raw
                        and (raw in clean(source.text) or masked)
                    ):
                        grounded, used = source, snippet["raw_text"]
                        break
                if grounded:
                    break
        if grounded:
            if path == "bank_account_last4":
                used = re.sub(r"[0-9]{5,}", lambda match: "****" + match.group()[-4:], used)
            evidence.append(
                Evidence(
                    field=path,
                    raw_text=used,
                    page=grounded.page,
                    method="DERIVED" if grounded.derived else "TEXT",
                    verified=True,
                )
            )
        elif (
            value is None
            and candidates
            and path in ("vendor_tax_id", "po_reference", "bank_account_last4")
        ):
            findings.append("PRINTED_FIELD_OMITTED")
        elif value is None and candidates and path.endswith((".sku", ".po_line_no")):
            findings.append("PRINTED_FIELD_OMITTED")
        provenance.append(
            dict(
                field=path,
                grounded=grounded is not None,
                method="DERIVED"
                if grounded and grounded.derived
                else "TEXT"
                if grounded
                else "VISION_OR_UNGROUNDED",
                page=grounded.page if grounded else None,
                calculation=grounded.calculation if grounded else None,
                pages=list(grounded.pages or (grounded.page,)) if grounded else [],
            )
        )
    if not any(page.strip() for page in local.pages):
        findings.append("SCANNED_EVIDENCE_REQUIRES_REVIEW")
    if data["currency"] != "INR":
        findings.append("UNSUPPORTED_OR_MISSING_CURRENCY")
    data["tax_mode"] = data["tax_mode"] or "UNKNOWN"
    data["evidence"] = evidence
    try:
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
            if any(
                v is None
                for v in (
                    line.quantity,
                    line.unit_price,
                    line.tax_rate,
                    line.net_amount,
                    line.tax_amount,
                    line.gross_amount,
                )
            ):
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
            for index, amount in enumerate((line.net_amount, line.tax_amount, line.gross_amount)):
                sums[index] += amount
        if complete and tuple(sums) != (
            document.subtotal_net,
            document.tax_total,
            document.total_gross,
        ):
            findings.append("HEADER_LINE_SUM_MISMATCH")
    blocking = set(findings)
    if document.currency is not None:
        # Scope is a financial check; a printed unsupported currency can still
        # have correctly grounded source evidence. Never convert its value.
        blocking.discard("UNSUPPORTED_OR_MISSING_CURRENCY")
    document = document.model_copy(update={"verification_findings": tuple(sorted(blocking))})
    return Verification(document, tuple(sorted(set(findings))), tuple(provenance))
