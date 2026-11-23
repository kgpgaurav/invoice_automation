"""Version 8 closes ambiguous/null financial component gaps; version 7 stays frozen."""

from app.evidence_legacy import Verification
from app.extended_verification_v7 import verify_extended as verify_v7


def financial_conflicts(checked):
    return [
        p["field"]
        for p in checked.provenance
        if p.get("state") == "AMBIGUOUS"
        and (
            p["field"].endswith(("_amount", "_rate"))
            or p["field"] in ("other_charges", "rounding_adjustment")
        )
    ]


def verify_extended(extraction, pdf, base):
    checked = verify_v7(extraction, pdf, base)
    conflicts = set(financial_conflicts(checked))
    if not conflicts:
        return checked
    findings = tuple(sorted(set(checked.findings) | {"UNVERIFIED_FINANCIAL_DETAIL"}))
    document = checked.document
    if document:
        document = document.model_copy(
            update={
                "verification_findings": tuple(
                    sorted(set(document.verification_findings) | {"UNVERIFIED_FINANCIAL_DETAIL"})
                )
            }
        )
    provenance = tuple(
        dict(p, required=True) if p["field"] in conflicts else p for p in checked.provenance
    )
    return Verification(document, findings, provenance)
