# PS-1 — Business Rules and Decision Policy (v1.0 draft)

**Status:** proposed conservative baseline to finalize before code. Rules are owned by deterministic Python services. An LLM must never assign a business decision. Policy values below are **chosen demonstration defaults, not regulatory or industry standards**.

## 1. Decision semantics

| Decision | Meaning | Operational output |
|---|---|---|
| `APPROVED` | All mandatory verifications passed within the frozen policy | Payment-ready CSV/record; no payment initiated |
| `NEEDS_REVIEW` | Missing, ambiguous or exception-triggering evidence needs a reviewer | Specific question + candidate evidence; LangGraph interrupt |
| `REJECTED` | Certain policy violation, such as already approved duplicate or cancelled PO | Plain-English reason + *draft* vendor/internal response |
| `FAILED` | Infrastructure/API/document-processing fault, not a financial assessment | Retryable or diagnosable technical error; never labeled as rejected |

No auto-approval for unknown supplier identity, ambiguous vendor/PO, unsupported currencies, missing invoice number/date/total, inconsistent arithmetic, or unverified critical fields.

## 2. Policy config (`policy_versions`)

```yaml
version: "policy-1.0"
currency_scope: [INR]              # USD support postponed until covered by fixtures
invoice_rounding_tolerance: "0.05" # INR absolute error for sums, not spend overage
line_rounding_tolerance: "0.02"    # INR per line
unit_price_auto_variance_pct: "0.50" # percent of PO unit price, subject to remaining-balance cap
unit_price_review_variance_pct: "2.00" # greater variance still review, not automatic fraud verdict
po_amount_overrun_auto: "0.00"     # never auto-approve a spend-cap overrun
allow_implicit_po_auto_match: false # conservative initial setting; human picks
allow_header_only_auto_approval: false
allow_future_dated_invoice: false
max_future_date_days: 0
max_llm_extraction_attempts: 2
```

Do **not** interpret tolerance as permission to increase PO spending. Rounding tolerance verifies document arithmetic. Price tolerance is a comparison aid; final invoice amount must still fit the PO's available cap and quantities.

## 3. Decision rule order

**R00 — Safe document intake:** genuine readable PDF, <= 12 MiB, <= 5 pages, not encrypted. Invalid uploads fail before queueing (HTTP error), and uploaded content is never executed.

**R01 — Critical extraction:** require vendor identifier/name, invoice number, date, currency, and total. Empty or inconsistent critical fields -> `NEEDS_REVIEW`; never guess. Only one targeted re-extraction is permitted; model escalation is optional and must be benchmarked.

**R02 — Supplier identity:** resolve by verified normalized tax ID when present; use PO-vendor association and normalized legal name as corroboration. Multiple matches, inactive master, or conflicting identifiers -> `NEEDS_REVIEW`. Invoice claimed vendor not matching explicit PO vendor -> `REJECTED` with `PO_VENDOR_MISMATCH` (unless extraction ambiguity -> review first). Optional bank last-four mismatch -> `NEEDS_REVIEW`, not an accusation of fraud.

**R03 — Duplicate:** compare `(vendor_id, normalized_invoice_number)` against canonical invoices. Previously `APPROVED` same business key -> `REJECTED` with `DUPLICATE_APPROVED`; if amount/date/hash conflict or canonical invoice is still pending, -> `NEEDS_REVIEW`. Detect normalization aliases (`INV-001` / `INV 001`); exact document hash is additional evidence. Database unique constraint and unique ledger ensure concurrency safety.

**R04 — PO selection:** if an explicit PO exists, verify vendor, status, currency, and valid date. If reference absent, list candidate open POs for verified vendor with same currency; rank deterministically by overlapping line identifiers, allowed amounts, and PO issue date. **v1: no implied PO automatic match** (`allow_implicit_po_auto_match=false`): ask reviewer to select if >0 candidates. Unknown PO -> `NEEDS_REVIEW`, never invent one.

**R05 — Dates/status:** invoice date in future -> `NEEDS_REVIEW`; before PO issued -> `NEEDS_REVIEW`; closed, cancelled or expired PO -> `REJECTED` if confirmed. Unknown date -> review. Demo policies do not claim legal tax-date compliance.

**R06 — Arithmetic:** use `Decimal`. For tax-exclusive invoices with net subtotal + tax, assert `abs(subtotal_net + tax_total - total_gross) <= 0.05`. For tax-inclusive invoices, only assert net + tax when net is explicitly a pre-tax net; otherwise verify available inclusive totals and mark unsupported ambiguity for review. For each item, `quantity * unit_price` should match `line_net` within `0.02` after the documented rounding strategy; if line gross and tax exist, compare them too. A missing or ambiguous itemization -> review by default.

**R07 — PO line matching:** match SKU/line ID first, then exact-normalized description; fuzzy description is **candidate generation only**. Quantity must not exceed PO line remaining quantity. Allowed unit-price deviation <=0.50% for auto-approval; above that -> review. Matching must never be based solely on vendor name and similar amount.

**R08 — Spend cap:** PO `approved_cap` and invoice `total_gross` are **both tax-inclusive gross values** in v1. Inside a DB transaction lock PO row (`SELECT ... FOR UPDATE`), recompute available = cap - committed_total; `total_gross <= available` required for automatic approval. No review-stage reservation. On exception approval, an authorized reviewer can override *matching* but **cannot exceed PO cap** unless a new approved PO amendment is created; demo implementation will not implement cap override.

**R09 — Finalize:** unique invoice ledger insert and PO committed balances update in one transaction. If constraint conflict/concurrent usage changes, re-evaluate or route review. Approval output contains policy version, exact calculation, PO, matched line references, and human-readable reason. No email is sent automatically.

## 4. Human review permissions and behavior

Allowed actions: `SELECT_PO`, `CORRECT_FIELD`, `REQUEST_INFO`, `REJECT_INVOICE`, and `APPROVE_EXCEPTION` only for a permitted exception (e.g. invoice date clarification or authorized line description mismatch). All reviews record actor, time, old/new field, and reason. `APPROVE_EXCEPTION` always re-enters the business-rule engine and cannot bypass a hard invariant. Selecting a PO does **not** automatically approve an invoice; the graph resumes at verification and matching. Critical value corrections need evidence; never silently mutate extraction.

**Hard boundaries:** no reviewer button can waive the PO cap, vendor identity mismatch, prior approved duplicate, or unsupported currency in v1. A reviewer may reject after reviewing an exception. As a demo, review actions use authenticated reviewer role; there is no anonymous approval endpoint.

## 5. Concrete decision examples

| Scenario | Expected outcome | Why |
|---|---|---|
| PO balance ₹50,000; valid invoice ₹48,000 | `APPROVED` | Verified vendor, PO, lines, arithmetic, within remaining cap |
| PO balance ₹50,000; invoice ₹50,001 | `NEEDS_REVIEW` | Cap exceeded; must obtain PO amendment, cannot auto-approve |
| `INV 001` already approved as `INV-001` | `REJECTED` | Normalized duplicate, regardless of file hash |
| Missing PO but two plausible POs | `NEEDS_REVIEW` | Human must select; then revalidate |
| Line item 100 x ₹100; declared ₹10,400 | `NEEDS_REVIEW` | Arithmetic contradiction not resolved by model confidence |
| PO belongs to vendor B; invoice claims vendor A | `REJECTED` if identity confirmed | PO/vendor mismatch |
| Invoice appears valid but PO was consumed by another run | `NEEDS_REVIEW` | Last transactional recheck catches race |
| Scanned invoice without reliable grand total | `NEEDS_REVIEW` | No guessed total |

## 6. Deterministic user-facing reason format

Each rule emits `RuleFinding {code, outcome: PASS|WARN|FAIL, expected, observed, explanation, evidence_refs}`. The finalizer constructs a concise explanation from these findings; the LLM may optionally rewrite a **draft** email but never alter the values or verdict.

Example: "Review required: INV-0082 requests ₹52,000 against PO-2041 remaining ₹50,000, an excess of ₹2,000. The policy prohibits automatic approval above the remaining balance."

## 7. Testable invariants

- Arithmetic and currency comparisons use `Decimal` and explicit two-decimal quantization.
- No two concurrent approvals can over-commit one PO.
- Replays and duplicate HTTP requests do not create a second ledger posting.
- Policy is snapshotted per run. Editing a policy does not retroactively change old decisions; a new `reevaluate` run explicitly references a new version.
- `REJECTED` is not a catch-all for timeout, corrupt PDF, or schema failure.
