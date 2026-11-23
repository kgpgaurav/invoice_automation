"""Versioned verification plus diagnostics; diagnostic states never confer approval."""

from pydantic import ValidationError

from app.evidence_layout_v4 import (
    LEGACY_VERIFIER_VERSION,
    Verification,
    labelled_records,  # noqa: F401
    matches,
)
from app.evidence_layout_v4 import verify as layout_verify
from app.evidence_layout_v6 import verify as semantic_verify
from app.evidence_legacy import ALIASES, NUMERIC, value_matches  # noqa: F401
from app.finance_contracts import FinancialDocument
from app.pdf_input import inspect_pdf
from app.source_layout import clean, inspect_layout, number
from app.source_layout_v6 import inspect_layout as semantic_layout

LAYOUT_VERIFIER_VERSION = "layout-grounding-4"
VERIFIER_VERSION = "extended-diagnostics-8"
DIAGNOSTIC_VERIFIERS = (
    "layout-diagnostics-5",
    "semantic-diagnostics-6",
    "extended-diagnostics-7",
    VERIFIER_VERSION,
)
LAYOUT_VERIFIERS = (LAYOUT_VERIFIER_VERSION, *DIAGNOSTIC_VERIFIERS)
SUPPORTED_VERIFIERS = (LEGACY_VERIFIER_VERSION, *LAYOUT_VERIFIERS)

REASONS = {
    "SOURCE_VERIFIED": "The extracted value has independently associated PDF text support.",
    "SOURCE_DERIVED": "Calculated locally from associated PDF values; see the recorded formula.",
    "NOT_EXTRACTED": "No value was extracted. This does not prove it is absent from the PDF.",
    "PRINTED_VALUE_NOT_EXTRACTED": (
        "Local source text identifies this field, but no value was extracted."
    ),
    "SOURCE_CONFLICT": "Local source values conflict; human review is required.",
    "NO_LOCAL_TEXT": "No local text evidence is available; visual extraction remains unverified.",
    "SOURCE_ASSOCIATION_UNSUPPORTED": (
        "A value was extracted, but local verification could not associate it with this field."
    ),
    "SOURCE_VALUE_MISMATCH": "The extracted value differs from its local source association.",
    "CITATION_UNVERIFIED": (
        "The value matches a local source association, but its citation/page could not be verified."
    ),
}


def raw_fields(extraction):
    data = extraction.model_dump()
    fields = {k: v for k, v in data.items() if k not in ("evidence", "line_items")}
    for index, line in enumerate(data["line_items"], 1):
        fields.update({f"lines.{index}.{k}": v for k, v in line.items() if k != "line_no"})
    return fields


def required_field(path, raw):
    name = path.rsplit(".", 1)[-1]
    if name in ("vendor_tax_id", "po_reference", "bank_account_last4", "sku", "po_line_no"):
        return raw is not None
    return True


def _verify_frozen(extraction, pdf, *, version="semantic-diagnostics-6"):
    if version not in SUPPORTED_VERIFIERS:
        raise ValueError("Unsupported frozen evidence verifier")
    semantic = version == "semantic-diagnostics-6"
    checked = (semantic_verify if semantic else layout_verify)(
        extraction,
        pdf,
        version=LEGACY_VERIFIER_VERSION
        if version == LEGACY_VERIFIER_VERSION
        else "semantic-grounding-6"
        if semantic
        else LAYOUT_VERIFIER_VERSION,
    )
    if version not in DIAGNOSTIC_VERIFIERS:
        return checked
    local = inspect_pdf(pdf)
    layout = (semantic_layout if semantic else inspect_layout)(pdf, local.pages)
    original = raw_fields(extraction)
    previous = {p["field"]: p for p in checked.provenance}
    normalized = raw_fields(extraction)
    if checked.document:
        document = checked.document.model_dump(mode="json")
        normalized.update({k: v for k, v in document.items() if k in original})
        for index, line in enumerate(document["lines"], 1):
            normalized.update({f"lines.{index}.{k}": v for k, v in line.items() if k != "line_no"})
    # Labelled verification uses printed numbers; diagnostics use extraction positions.
    labelled = (
        not layout.tables
        and {"vendor_name", "invoice_number", "total_gross"} <= labelled_records(local.pages).keys()
    )
    provenance = []
    for path, raw in original.items():
        lookup = path
        if labelled and path.startswith("lines."):
            _, index, key = path.split(".")
            printed = extraction.line_items[int(index) - 1].line_no
            lookup = f"lines.{printed}.{key}"
        prior = previous.get(lookup, {})
        candidates = layout.records.get(lookup, [])
        values = {
            number(s.value) if path.rsplit(".", 1)[-1] in NUMERIC else clean(s.value)
            for s in candidates
        }
        # Sender regions contain several name candidates; existing verification
        # disambiguates by the extracted name, not arbitrary page-wide equality.
        conflict = path != "vendor_name" and len(values) > 1
        value = normalized.get(path)
        source = layout.one(lookup)
        if value in (None, "UNKNOWN") and prior.get("grounded") and source:
            value = source.value
            normalized[path] = value
        if prior.get("grounded"):
            state = "DERIVED" if prior.get("method") == "DERIVED" else "EXTRACTED"
            reason = "SOURCE_DERIVED" if state == "DERIVED" else "SOURCE_VERIFIED"
        elif conflict:
            state, reason = "AMBIGUOUS", "SOURCE_CONFLICT"
        elif value is None or value == "UNKNOWN":
            state = "MISSING" if value is None else "AMBIGUOUS"
            reason = "PRINTED_VALUE_NOT_EXTRACTED" if candidates else "NOT_EXTRACTED"
        elif not any(p.strip() for p in local.pages):
            state, reason = "UNVERIFIED", "NO_LOCAL_TEXT"
        elif not candidates:
            state, reason = "UNVERIFIED", "SOURCE_ASSOCIATION_UNSUPPORTED"
        elif not any(matches(path, value, s) for s in candidates):
            state, reason = "UNVERIFIED", "SOURCE_VALUE_MISMATCH"
        else:
            state, reason = "UNVERIFIED", "CITATION_UNVERIFIED"
        provenance.append(
            dict(
                prior,
                field=path,
                grounded=bool(prior.get("grounded")),
                state=state,
                reason_code=reason,
                reason=REASONS[reason],
                original_value=raw if path != "bank_account_last4" else None,
                normalized_value=value if path != "bank_account_last4" else None,
                required=required_field(path, raw),
                source_candidate_count=len(candidates),
                candidate_pages=sorted({s.page for s in candidates}),
            )
        )
    if checked.document is None:
        # Financial typing is separate from source support. Preserve exact error
        # categories without Pydantic's raw inputs, contexts or arbitrary messages.
        data = extraction.model_dump(exclude={"evidence", "line_items"})
        data.update({k: v for k, v in normalized.items() if not k.startswith("lines.")})
        data["tax_mode"] = data["tax_mode"] or "UNKNOWN"
        data["lines"] = [
            dict(
                line.model_dump(),
                line_no=i,
                **{
                    k: normalized.get(f"lines.{i}.{k}", v)
                    for k, v in line.model_dump().items()
                    if k != "line_no"
                },
            )
            for i, line in enumerate(extraction.line_items, 1)
        ]
        try:
            FinancialDocument.model_validate(data)
        except ValidationError as error:
            for issue in error.errors(include_input=False, include_context=False):
                loc = list(issue["loc"])
                if len(loc) > 1 and loc[0] == "lines" and isinstance(loc[1], int):
                    loc[1] += 1
                path = ".".join(map(str, loc))
                for field in provenance:
                    if field["field"] == path:
                        field.setdefault("financial_validation_errors", []).append(issue["type"])
    return Verification(checked.document, checked.findings, tuple(provenance))


def verify(extraction, pdf, *, version=VERIFIER_VERSION):
    if version == "extended-diagnostics-7":
        from app.extended_verification_v7 import verify_extended

        return verify_extended(extraction, pdf, lambda wire: _verify_frozen(wire, pdf))
    if version != VERIFIER_VERSION:
        return _verify_frozen(extraction, pdf, version=version)
    from app.extended_verification import verify_extended

    return verify_extended(extraction, pdf, lambda wire: _verify_frozen(wire, pdf))


def repair_fields(checked):
    """Only retry errors a field correction can resolve. Never invent associations."""
    if set(checked.findings) & {
        "SCANNED_EVIDENCE_REQUIRES_REVIEW",
        "SCANNED_DOCUMENT_REQUIRES_REVIEW",
    }:
        return []
    if set(checked.findings) & {
        "ARITHMETIC_MISMATCH",
        "LINE_ARITHMETIC_MISMATCH",
        "HEADER_LINE_SUM_MISMATCH",
    } and not any(p.get("reason_code") == "SOURCE_VALUE_MISMATCH" for p in checked.provenance):
        return []
    return [
        p["field"]
        for p in checked.provenance
        if p.get("state") in ("MISSING", "UNVERIFIED", "AMBIGUOUS")
        and p.get("reason_code") not in ("SOURCE_CONFLICT", "SOURCE_ASSOCIATION_UNSUPPORTED")
        and p.get("source_candidate_count", 0) > 0
        and (p.get("required") or p.get("reason_code") == "PRINTED_VALUE_NOT_EXTRACTED")
    ]
