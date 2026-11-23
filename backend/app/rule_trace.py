"""Executed financial checks captured inside the assessment transaction."""

TITLES = (
    ("REQUIRED_FIELDS", "Essential invoice fields"),
    ("SOURCE_EVIDENCE", "Fields supported by the PDF"),
    ("VENDOR_IDENTITY", "Supplier identity matches the vendor record"),
    ("VENDOR_STATUS", "Supplier is approved"),
    ("BANK_DETAILS", "Printed bank details match"),
    ("DUPLICATE_IDENTITY", "No previously approved invoice with this identity"),
    ("PO_MATCH", "Referenced purchase order matches the supplier"),
    ("PO_STATUS_DATE", "Purchase order status and dates"),
    ("INVOICE_ARITHMETIC", "Invoice line and total arithmetic"),
    ("TAX_RECONCILIATION", "Tax rates and amounts match the PO"),
    ("PO_PRICE", "Unit prices match the PO"),
    ("PO_QUANTITY", "Quantities fit the remaining PO allowance"),
    ("PO_BALANCE", "Invoice fits the remaining PO balance"),
)
CODE_RULE = {
    "CRITICAL_FIELD_MISSING": "REQUIRED_FIELDS",
    "UNVERIFIED_TOTAL": "SOURCE_EVIDENCE",
    "SCANNED_DOCUMENT_REQUIRES_REVIEW": "SOURCE_EVIDENCE",
    "FINANCIAL_ADJUSTMENT_REQUIRES_REVIEW": "INVOICE_ARITHMETIC",
    "VENDOR_UNKNOWN": "VENDOR_IDENTITY",
    "VENDOR_ID_MISMATCH": "VENDOR_IDENTITY",
    "VENDOR_INACTIVE": "VENDOR_STATUS",
    "VENDOR_BLACKLISTED": "VENDOR_STATUS",
    "BANK_MISMATCH": "BANK_DETAILS",
    "DUPLICATE_APPROVED": "DUPLICATE_IDENTITY",
    "DUPLICATE_CONFLICT": "DUPLICATE_IDENTITY",
    "PO_MISSING": "PO_MATCH",
    "PO_AMBIGUOUS": "PO_MATCH",
    "PO_VENDOR_MISMATCH": "PO_MATCH",
    "UNSUPPORTED_CURRENCY": "PO_MATCH",
    "PO_CLOSED": "PO_STATUS_DATE",
    "FUTURE_DATE": "PO_STATUS_DATE",
    "DATE_BEFORE_PO": "PO_STATUS_DATE",
    "ARITHMETIC_MISMATCH": "INVOICE_ARITHMETIC",
    "TAX_UNCLEAR": "TAX_RECONCILIATION",
    "PRICE_VARIANCE": "PO_PRICE",
    "LINE_AMBIGUOUS": "PO_QUANTITY",
    "QTY_EXCEEDED": "PO_QUANTITY",
    "PO_CAP_EXCEEDED": "PO_BALANCE",
    "ALLOCATION_CONFLICT": "PO_BALANCE",
}


class RuleTrace:
    def __init__(self):
        self.rows = {
            key: dict(
                rule_id=key,
                title=title,
                status="not_evaluated",
                description="Awaiting prerequisite checks.",
                finding_code=None,
            )
            for key, title in TITLES
        }

    def passed(self, key, description):
        self.rows[key].update(status="passed", description=description)

    def stop(self, result):
        key = CODE_RULE.get(result.code)
        if key:
            self.rows[key].update(
                status="failed" if result.decision == "REJECTED" else "requires_review",
                description=result.reason,
                finding_code=result.code,
            )
        for row in self.rows.values():
            if (
                row["status"] == "not_evaluated"
                and row["description"] == "Awaiting prerequisite checks."
            ):
                row["description"] = (
                    f"Not checked: resolve {result.code.lower().replace('_', ' ')} first."
                )
        return list(self.rows.values())
