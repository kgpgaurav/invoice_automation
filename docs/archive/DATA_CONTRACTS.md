# PS-1 — Data Contracts (v1.0 draft)

**Status:** proposed implementation contract, not implemented.  **Scope:** invoice PDFs against a seeded purchase-order (PO) register.  **Last reviewed:** 2026-11-11.

## Principles

1. OpenAI extracts facts; only Python code and authorized human reviewers decide. Never ask the LLM to output `APPROVED` or `REJECTED`.
2. Raw extraction must preserve uncertainty. Missing or unreadable fields are `null`, not inferred values. Source evidence is attached to critical fields.
3. All financial values are `Decimal` in Python and `NUMERIC(18, 2)` in PostgreSQL for v1. JSON represents money and quantities as decimal **strings**, never binary floats.
4. Dates use ISO 8601 `YYYY-MM-DD` and timestamps use UTC ISO 8601; original display formats may be retained as evidence.
5. UUIDs identify business entities and jobs. Business keys such as invoice numbers are not globally unique.
6. PDF bytes live in private persistent object storage or an abstracted binary store; graph checkpoints keep metadata and references, not PDF bytes.
7. All schemas are explicitly versioned: `extraction_schema_version`, `business_policy_version`, `prompt_version`, and `model_id`.

## A. Extraction result — OpenAI Structured Outputs

`ExtractedInvoiceV1` is the data structure returned by the model. Every field is present in the JSON schema; nullable means `null` is legitimate. Do not use LLM-supplied confidence numbers as approval gates.

| Field | Type | Required for automatic approval? | Notes |
|---|---|---|---|
| `vendor_name` | `str?` | Yes | Must resolve to an active vendor via ID/PO, not name alone |
| `vendor_tax_id` | `str?` | Policy-dependent | Prefer normalized tax identifier if present |
| `invoice_number` | `str?` | Yes | Preserve original case/spaces as printed |
| `invoice_date` | `date?` | Yes | No inferred dates |
| `po_reference` | `str?` | No | May be implicit/missing; use candidate selection flow |
| `currency` | ISO 4217 `str?` | Yes | Same-currency matching only; no FX in v1 |
| `subtotal_net` | decimal string or `null` | Conditional | Pre-tax subtotal, only when explicitly identifiable |
| `tax_total` | decimal string or `null` | Conditional | Sum of explicitly identifiable tax amounts |
| `total_gross` | decimal string or `null` | Yes | Amount payable |
| `tax_mode` | `EXCLUSIVE / INCLUSIVE / UNKNOWN` | Yes | `UNKNOWN` triggers review if arithmetic cannot be established |
| `line_items` | array of `InvoiceLineV1` | Conditional | Bundled lines may force header-only review |
| `bank_account_last4` | `str?` | No | Illustrative fraud signal, do not store full account in logs |
| `source_evidence` | array of `FieldEvidenceV1` | Yes for critical fields | Supports review/highlighting, not proof of correctness |

`InvoiceLineV1`:
- `line_no: int`, `description: str?`, `sku: str?`, `quantity: decimal-string?`, `unit: str?`, `unit_price: decimal-string?`, `line_net: decimal-string?`, `tax_amount: decimal-string?`, `line_gross: decimal-string?`.
- If a document does not itemize, return `line_items=[]` rather than inventing a line.
- Quantities allow up to 4 decimal places internally; money rounds only at documented boundaries.

`FieldEvidenceV1`:
- `field_path: str` (e.g. `total_gross` or `line_items[0].unit_price`)
- `page_number: int?` (1-based)
- `source_quote: str?` (brief exact-looking content copied from the document)
- `evidence_mode: TEXT_LAYER | VISUAL | BOTH`
- `bbox: [x0,y0,x1,y1]?` (populated by local text search when possible, not invented by model)
- `verification: FOUND_IN_TEXT | VISUAL_ONLY | NOT_FOUND | NOT_CHECKED` (populated in Python)

**Evidence rule:** a text match improves traceability but is never sufficient for approval. Visual-only evidence is allowed, but uncertainty or conflicting figures routes to human review. The UI must distinguish verified text-layer highlights from visually identified page references.

### Illustrative extraction payload

```json
{
  "vendor_name": "Acme Components Pvt Ltd",
  "vendor_tax_id": "29ABCDE1234F1Z5",
  "invoice_number": "INV-0042",
  "invoice_date": "2026-11-05",
  "po_reference": "PO-2041",
  "currency": "INR",
  "subtotal_net": "10000.00",
  "tax_total": "1800.00",
  "total_gross": "11800.00",
  "tax_mode": "EXCLUSIVE",
  "line_items": [
    {"line_no": 1, "description": "Precision bolts", "sku": "BOLT-12", "quantity": "100", "unit": "pcs", "unit_price": "100.00", "line_net": "10000.00", "tax_amount": "1800.00", "line_gross": "11800.00"}
  ],
  "bank_account_last4": null,
  "source_evidence": [
    {"field_path":"invoice_number", "page_number":1, "source_quote":"Invoice No: INV-0042", "evidence_mode":"TEXT_LAYER", "bbox":null, "verification":"NOT_CHECKED"},
    {"field_path":"total_gross", "page_number":1, "source_quote":"Grand Total ₹11,800.00", "evidence_mode":"TEXT_LAYER", "bbox":null, "verification":"NOT_CHECKED"}
  ]
}
```

The example is *illustrative*, not a test of the GSTIN or data pipeline. OpenAI may return `null` instead of a value it cannot support.

## B. Application/database tables

| Table | Essential columns | Constraints and purpose |
|---|---|---|
| `vendors` | `id`, `legal_name`, `normalized_tax_id`, `status`, `bank_last4`, `created_at` | Unique non-null normalized tax ID per jurisdiction, `ACTIVE/INACTIVE`; master records are seeded |
| `purchase_orders` | `id`, `po_number`, `vendor_id`, `currency`, `issued_at`, `expires_at?`, `status`, `approved_cap`, `committed_total`, `version` | Unique PO number, FK vendor; all PO caps and committed amounts are tax-inclusive gross; remaining balance is `cap - committed_total`, never LLM-derived |
| `purchase_order_lines` | `id`, `po_id`, `line_no`, `sku?`, `description`, `quantity`, `unit_price`, `committed_quantity` | Unique `(po_id,line_no)`; supports line-level checks |
| `invoices` | `id`, `vendor_id`, `normalized_invoice_number`, `original_invoice_number`, `invoice_date`, `currency`, `gross`, `canonical_run_id`, `status` | One canonical registered invoice per `(vendor_id, normalized_invoice_number)`; **do not create a second canonical invoice for a duplicate** |
| `runs` | `id`, `document_sha256`, `document_uri`, `job_state`, `decision`, `decision_reason`, `thread_id`, `policy_version`, `prompt_version`, `extractor_model`, `created_at`, `updated_at`, `error_code?` | Many runs may reference one document/invoice; `job_state` separate from `decision` |
| `run_events` | `id`, `run_id`, `seq`, `type`, `stage`, `payload_json`, `created_at` | Unique `(run_id,seq)`; append only; sanitized payloads |
| `review_requests` | `id`, `run_id`, `kind`, `question`, `options_json`, `status`, `created_at`, `resolved_at?` | Single actionable pending question per run in MVP |
| `review_actions` | `id`, `review_request_id`, `actor_id`, `action`, `payload_json`, `created_at`, `idempotency_key` | Reviewer actions are immutable; unique request idempotency key |
| `approval_ledger` | `id`, `invoice_id`, `po_id`, `run_id`, `gross`, `created_at` | Unique `invoice_id`; only place an approved amount is committed |
| `policy_versions` | `version`, `config_json`, `created_at`, `created_by` | Immutable snapshots; never silently change rules for existing runs |
| `run_queue` | `run_id`, `work_type`, `attempts`, `lease_until?`, `claimed_by?`, `next_attempt_at`, `status` | Durable work queue for process/resume; no Redis required for MVP |
| `api_usage` | `id`, `run_id`, `model_id`, `input_tokens`, `cached_input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `prompt_version` | Per-call metering and estimation; never expose API key |

### Domain enums

- `RunJobState = QUEUED | PREPROCESSING | EXTRACTING | VERIFYING | MATCHING | EVALUATING | WAITING_REVIEW | FINALIZING | COMPLETED | FAILED`.
- `BusinessDecision = APPROVED | NEEDS_REVIEW | REJECTED | null`. `null` while running. `FAILED` is a technical run state, **not** a business rejection.
- `POStatus = OPEN | CLOSED | CANCELLED | EXPIRED`.
- `VendorStatus = ACTIVE | INACTIVE`.
- `ReviewKind = SELECT_PO | CORRECT_FIELD | APPROVE_EXCEPTION | REJECT_INVOICE | REQUEST_INFO`.

## C. Normalization and deduplication

- `vendor_tax_id`: uppercase and whitespace-normalize, then jurisdiction-specific format/checksum checks where implemented. Tax ID is an identity clue, **not** proof of legal existence.
- `normalized_invoice_number`: Unicode NFKC, trim, uppercase, strip spaces and common separators `- _ / .`. E.g. `INV 001`, `inv-001`, `INV/001` normalize to `INV001`. Because normalization can collide, suspected duplicates with conflicting data go to review.
- File SHA-256 detects identical bytes only; it does not detect rescans. Document hash by itself must not decide financial uniqueness.
- An exact retry with the same user idempotency key returns the original run; a new submission with a reused invoice business key is separately audited but cannot create another approved ledger entry.

## D. Invariants

1. Only `COMPLETED + APPROVED` runs produce `approval_ledger` rows.
2. `approval_ledger.invoice_id` is unique; approving/resuming twice cannot commit twice.
3. `purchase_orders.committed_total` equals the sum of ledger rows for that PO (reconciliation test).
4. A reviewer action does **not** reserve PO capacity. Recheck available balance under row lock before final approval.
5. Only a matched **active vendor + open PO + matching currency** can be auto-approved.
6. Inputs from PDFs are untrusted. Prompt-injection text is treated as document content; no tools/payment endpoints are exposed to the extractor.
7. Provider-specific response metadata lives in `api_usage`, not in business entities.

## E. Out of scope for v1

No money transfer; no real ERP modification; no live vendor verification service; no actual vendor email sending; no foreign-exchange conversion; no three-way goods-receipt match. The result is **payment-ready for AP review/export**, never "paid".
