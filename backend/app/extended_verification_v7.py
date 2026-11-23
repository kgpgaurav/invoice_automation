"""New-run scan hold and expanded-field verification; frozen verifiers stay unchanged."""

import re
from decimal import Decimal, localcontext

from pydantic import TypeAdapter, ValidationError

from app.document_classification import scan_pages
from app.evidence_legacy import Verification
from app.extended_sources import inspect_extra_sources, parsed_number
from app.extraction_schema import EXTRA_HEADERS, EXTRA_LINES, InvoiceExtractionV1, InvoiceLineV1
from app.finance_contracts import Money, Rate, money
from app.pdf_input import inspect_pdf
from app.source_layout import Source, clean
from app.source_layout_v6 import inspect_layout

SCAN_HOLD = "SCANNED_DOCUMENT_REQUIRES_REVIEW"


def quantity_citations(core, pdf):
    """Ground number/unit quotes in their real page and independently located cell."""
    local = inspect_pdf(pdf)
    layout = inspect_layout(pdf, local.pages)
    if not layout.tables:
        return core
    numbered = [line["line_no"] for line in core["line_items"]]
    aliases = {
        str(value): index
        for index, value in enumerate(numbered, 1)
        if value is not None and numbered.count(value) == 1
    }
    for citation in core["evidence"]:
        path = re.fullmatch(r"lines\.([1-9][0-9]*)\.quantity", citation["field"])
        quote = re.fullmatch(
            r"([0-9,]+(?:\.[0-9]+)?)\s+[^\W\d_][\w./-]*", clean(citation["raw_text"])
        )
        if not path or not quote:
            continue
        index = aliases.get(path[1], int(path[1]))
        if index > len(core["line_items"]):
            continue
        source = layout.one(f"lines.{index}.quantity")
        if (
            source
            and source.page == citation["page"]
            and parsed_number(quote[1]) == parsed_number(source.value)
            and parsed_number(core["line_items"][index - 1]["quantity"])
            == parsed_number(source.value)
            and clean(citation["raw_text"]) in clean(local.pages[source.page - 1])
        ):
            # This is an actual local quote, never manufactured model evidence.
            # The untouched extraction/history retains the model's original quote.
            citation["raw_text"] = source.text
    return core


def verify_extended(extraction, pdf, base):
    original = extraction.model_dump()
    core = {k: original[k] for k in InvoiceExtractionV1.model_fields if k != "line_items"}
    core["line_items"] = [
        {k: line[k] for k in InvoiceLineV1.model_fields} for line in original["line_items"]
    ]
    checked = base(InvoiceExtractionV1.model_validate(quantity_citations(core, pdf)))
    sources, unresolved_adjustments = inspect_extra_sources(pdf, extraction)
    # Component calculations use independently supported net values and explicit
    # component rates; absent tax never defaults to zero.
    if checked.document:
        verified = {e.field for e in checked.document.evidence if e.verified}
        with localcontext() as context:
            context.prec = 48
            for kind in ("cgst", "sgst", "igst", "cess"):
                for i, line in enumerate(checked.document.lines, 1):
                    prefix = f"lines.{i}."
                    rates = sources.get(prefix + kind + "_rate", [])
                    if (
                        prefix + "net_amount" in verified
                        and line.net_amount is not None
                        and rates
                        and len({s.value for s in rates}) == 1
                        and prefix + kind + "_amount" not in sources
                    ):
                        value = money(line.net_amount * Decimal(rates[0].value) / 100)
                        sources[prefix + kind + "_amount"] = [
                            Source(
                                rates[0].page,
                                str(value),
                                rates[0].text,
                                True,
                                f"{line.net_amount} * {rates[0].value}% = {value}",
                            )
                        ]
                for suffix in ("amount", "rate"):
                    path = kind + "_" + suffix
                    rows = [
                        sources.get(f"lines.{i}.{path}", [])
                        for i in range(1, len(checked.document.lines) + 1)
                    ]
                    if (
                        path in sources
                        or not rows
                        or not all(r and len({s.value for s in r}) == 1 for r in rows)
                    ):
                        continue
                    values = [Decimal(r[0].value) for r in rows]
                    if suffix == "rate" and len(set(values)) != 1:
                        continue
                    value = sum(values, Decimal(0)) if suffix == "amount" else values[0]
                    sources[path] = [
                        Source(
                            rows[0][0].page,
                            str(value),
                            "\n".join(r[0].text for r in rows),
                            True,
                            (
                                "Sum of source-supported line component amounts"
                                if suffix == "amount"
                                else "All printed line component rates agree"
                            )
                            + f" = {value}",
                            tuple(sorted({r[0].page for r in rows})),
                        )
                    ]
    fields = {key: original.get(key) for key in EXTRA_HEADERS}
    for index, line in enumerate(original["line_items"], 1):
        fields.update({f"lines.{index}.{key}": line.get(key) for key in EXTRA_LINES})
    findings = set(checked.findings)
    if unresolved_adjustments:
        findings.add("UNVERIFIED_FINANCIAL_DETAIL")
    provenance = list(checked.provenance)
    normalized = {}
    for path, raw in fields.items():
        key = path.rsplit(".", 1)[-1]
        numeric = key.endswith(("_amount", "_rate")) or key in (
            "other_charges",
            "rounding_adjustment",
        )
        candidates = sources.get(path, [])

        def canonical(value):
            if value is None:
                return None
            if numeric:
                return parsed_number(value, signed=key == "rounding_adjustment")
            return re.sub(r"[\s,;]+", " ", clean(value)).strip().casefold()

        values = {canonical(s.value) for s in candidates}
        source = candidates[0] if len(values) == 1 else None
        value = raw if raw is not None else source.value if source else None
        grounded = source is not None and canonical(value) == canonical(source.value)
        normalized_value = value
        errors = []
        if grounded and numeric:
            parsed = canonical(value)
            try:
                if parsed is None:
                    raise ValueError("invalid numeric value")
                if key == "rounding_adjustment":
                    TypeAdapter(Money).validate_python(abs(parsed))
                else:
                    TypeAdapter(Rate if key.endswith("_rate") else Money).validate_python(parsed)
                normalized_value = str(parsed if key.endswith("_rate") else money(parsed))
            except (ValidationError, ValueError):
                grounded = False
                errors = ["invalid_decimal_or_precision"]
        # A supplied citation with a wrong page cannot confer verification.
        citations = [e for e in original["evidence"] if e["field"] == path]
        if grounded and citations and not any(e["page"] == source.page for e in citations):
            grounded = False
        if len(values) > 1:
            state, reason = "AMBIGUOUS", "SOURCE_CONFLICT"
        elif value is None:
            state, reason = "MISSING", "NOT_EXTRACTED"
        elif grounded:
            state, reason = (
                "DERIVED" if source.derived else "EXTRACTED",
                "SOURCE_DERIVED"
                if source.derived
                else "SOURCE_VERIFIED"
                if raw is not None
                else "SOURCE_LOCALLY_RECOVERED",
            )
        else:
            state, reason = (
                "UNVERIFIED",
                "SOURCE_ASSOCIATION_UNSUPPORTED" if not candidates else "SOURCE_VALUE_MISMATCH",
            )
        normalized[path] = normalized_value
        provenance.append(
            dict(
                field=path,
                grounded=grounded,
                state=state,
                reason_code=reason,
                reason="Supported by an independently associated PDF value."
                if grounded
                else "Source values conflict; human review is required."
                if state == "AMBIGUOUS"
                else "No value was extracted or independently established."
                if state == "MISSING"
                else "The saved value lacks independent field/page support.",
                method="DERIVED"
                if grounded and source.derived
                else "TEXT"
                if grounded
                else "VISION_OR_UNGROUNDED",
                page=source.page if grounded else None,
                pages=list(source.pages or (source.page,)) if grounded else [],
                original_value=raw,
                normalized_value=normalized_value,
                required=numeric and value is not None,
                source_candidate_count=len(candidates),
                candidate_pages=sorted({s.page for s in candidates}),
                calculation=source.calculation if grounded else None,
                financial_validation_errors=errors,
            )
        )
        if numeric and value is not None and not grounded:
            findings.add("UNVERIFIED_FINANCIAL_DETAIL")
        if grounded and key in (
            "discount_amount",
            "discount_rate",
            "shipping_amount",
            "other_charges",
            "rounding_adjustment",
        ):
            if Decimal(normalized_value) != 0:
                findings.add("FINANCIAL_ADJUSTMENT_REQUIRES_REVIEW")

    supported = {p["field"]: p for p in provenance if p.get("grounded")}
    document = checked.document
    if document:
        with localcontext() as context:
            context.prec = 48
            for prefix, total, rate in [("", document.tax_total, None)] + [
                (f"lines.{i}.", line.tax_amount, line.tax_rate)
                for i, line in enumerate(document.lines, 1)
            ]:
                components = [
                    normalized[prefix + k + "_amount"]
                    for k in ("cgst", "sgst", "igst", "cess")
                    if prefix + k + "_amount" in supported
                ]
                rates = [
                    normalized[prefix + k + "_rate"]
                    for k in ("cgst", "sgst", "igst", "cess")
                    if prefix + k + "_rate" in supported
                ]
                if (
                    components
                    and total is not None
                    and sum(map(Decimal, components), Decimal(0)) != total
                ):
                    findings.add("GST_COMPONENT_MISMATCH")
                if rates and rate is not None and sum(map(Decimal, rates), Decimal(0)) != rate:
                    findings.add("GST_COMPONENT_MISMATCH")
    if scan_pages(pdf):
        findings.add(SCAN_HOLD)
    if document:
        document = document.model_copy(
            update={
                "verification_findings": tuple(
                    sorted(set(document.verification_findings) | (findings - set(checked.findings)))
                ),
            }
        )
    return Verification(document, tuple(sorted(findings)), tuple(provenance))
