# PS-1 — API and Frontend Contract (v1.0 draft)

**Status:** proposed FastAPI HTTP/JSON + SSE contract. Base path `/api/v1`. Frontend is React + TypeScript. Generate TypeScript clients/types from FastAPI OpenAPI when implemented; **do not duplicate domain contracts by hand**.

## 1. Cross-cutting conventions

- IDs are UUID strings; server timestamps UTC ISO 8601; money values decimal strings with currency separated.
- All read/write endpoints for real invoice data require authentication. Reviewer and policy mutation routes require reviewer/admin role.
- Client `X-Idempotency-Key` optional on create/submit routes; use one key per user action; backend stores key with request fingerprint for 24h or more. Same key + same payload returns same resource; key + different payload -> `409`.
- `run.job_state` measures execution; `run.decision` measures the business conclusion. A workflow can be `WAITING_REVIEW` with `NEEDS_REVIEW`, or `COMPLETED` with `APPROVED`/`REJECTED`.
- Errors return `{ "error": { "code": "...", "message": "...", "details": {} }, "request_id": "..." }` (safe, non-secret).
- The UI must never infer business verdict from HTTP status. A successful HTTP 200 can contain `NEEDS_REVIEW`.

## 2. Endpoint inventory

| Method | Path | Body | Response | Notes |
|---|---|---|---|---|
| `POST` | `/invoices/process` | multipart PDF + optional input metadata | `202 Accepted` new run | Durable enqueue; no synchronous OpenAI invocation |
| `GET` | `/runs/{run_id}` | — | `200` run summary | Works during all states |
| `GET` | `/runs` | `?state=&decision=&limit=&cursor=` | `200` paged runs | Dashboard |
| `GET` | `/runs/{run_id}/events` | `?after_seq=0` | `200` event list | Polling fallback |
| `GET` | `/runs/{run_id}/events/stream` | `Last-Event-ID` optional | `200` `text/event-stream` | SSE with replay from stored sequence |
| `GET` | `/runs/{run_id}/document` | — | private PDF response | Same-origin/authenticated view; no public direct storage link |
| `GET` | `/runs/{run_id}/review` | — | `200` review request or `404` | Exact actionable question/candidates |
| `POST` | `/reviews/{review_request_id}/respond` | action + payload + reason | `202` | Persists action and enqueues resume; never commits PO inline |
| `GET` | `/purchase-orders` | `?vendor_id=` | `200` sanitized PO list | Inspector for demo |
| `GET` | `/policies/current` | — | `200` immutable policy snapshot | Viewer |
| `POST` | `/policies` | whole versioned policy | `201` | Admin-only; new immutable version, never overwrite |
| `POST` | `/runs/{run_id}/reevaluate` | `{policy_version?}` | `202` new run | Allowed for rejected/review cases; reuse vetted extraction if prompt/schema/data unchanged; new decision, re-lock PO |
| `GET` | `/runs/{run_id}/export` | — | CSV or `409` | Only for approved runs; represents payment-ready handoff |
| `GET` | `/healthz` | — | `200` status | Liveness; `/readyz` checks dependencies |

Reevaluation of an already APPROVED invoice returns `409`; never post an approval twice. Review/rejected cases can be reevaluated in a **new run** with a new policy snapshot. A new approval after review still passes all hard rules and the ledger lock.

Note: invoice document ingestion via email is deliberately not in v1. Existing pipeline later can call the same process service.

## 3. Create run

`POST /api/v1/invoices/process` with `Content-Type: multipart/form-data`:

```text
file: invoice.pdf
source: "MANUAL_UPLOAD"
```

Response `202`:

```json
{
  "run_id": "a8f1d39e-1c58-4273-b011-faf006f730bb",
  "job_state": "QUEUED",
  "decision": null,
  "created_at": "2026-11-11T10:00:00Z",
  "links": {
    "run": "/api/v1/runs/a8f1d39e-1c58-4273-b011-faf006f730bb",
    "events": "/api/v1/runs/a8f1d39e-1c58-4273-b011-faf006f730bb/events/stream"
  }
}
```

Expected intake errors: `413` file too large; `415` invalid media/signature; `422` encrypted/corrupt PDF or page limit; `401/403` unauthorized; `409` idempotency-key mismatch; `503` storage/DB unavailable before creation.

## 4. Run summary

`GET /api/v1/runs/{run_id}`:

```json
{
  "run_id": "a8f1d39e-1c58-4273-b011-faf006f730bb",
  "job_state": "WAITING_REVIEW",
  "decision": "NEEDS_REVIEW",
  "document_name": "invoice_82.pdf",
  "invoice": {
    "invoice_number": "INV-0082",
    "vendor_name": "Acme Components Pvt Ltd",
    "currency": "INR",
    "total_gross": "52000.00"
  },
  "matched_po": {"po_number": "PO-2041", "remaining_before_decision": "50000.00"},
  "rule_findings": [
    {"code":"PO_CAP_EXCEEDED","outcome":"FAIL","observed":"52000.00","expected":"<=50000.00","explanation":"Invoice exceeds remaining PO amount by INR 2000.00"}
  ],
  "review_request_id": "1c5bb35b-d3ef-479b-a312-8f8fcb1b53bc",
  "cost_usd": "0.000750",
  "execution_ms": 4800,
  "policy_version": "policy-1.0",
  "prompt_version": "extract-v1",
  "created_at": "2026-11-11T10:00:00Z"
}
```

All example values are illustrations, not actual API results or benchmark measurements. `execution_ms` excludes human waiting time; dashboard must label this.

## 5. Human review interaction

`GET /api/v1/runs/{run_id}/review` returns:

```json
{
  "review_request_id": "1c5bb35b-d3ef-479b-a312-8f8fcb1b53bc",
  "kind": "SELECT_PO",
  "question": "Invoice has no PO reference. Which purchase order applies?",
  "options": [
    {"po_id":"00000000-0000-4000-8000-000000000001","po_number":"PO-2041","remaining":"50000.00"},
    {"po_id":"00000000-0000-4000-8000-000000000002","po_number":"PO-2048","remaining":"60000.00"}
  ],
  "allowed_actions": ["SELECT_PO", "REJECT_INVOICE", "REQUEST_INFO"],
  "status": "OPEN"
}
```

`POST /api/v1/reviews/{review_request_id}/respond`:

```json
{
  "action": "SELECT_PO",
  "payload": {"po_id":"00000000-0000-4000-8000-000000000001"},
  "reason": "Purchase order confirmed against the attached parts list"
}
```

Response `202` includes `run_id`, `job_state: QUEUED`, and `queued_resume: true`. Client must not optimistically mark approved. Use `409` for already-resolved review or stale state, `422` for disallowed action/candidate, `403` for insufficient role.

## 6. SSE contract and fallback

`GET /runs/{id}/events/stream` sends canonical persisted events:

```text
id: 9
event: STAGE_FINISHED
data: {"run_id":"...","seq":9,"stage":"VERIFYING","type":"STAGE_FINISHED","payload":{"outcome":"PASS"}}

```

- SSE `id` is persisted `seq`; on reconnect read `Last-Event-ID` to replay missed events. Support `?after_seq=` for clients where header cannot be set.
- Send heartbeat comments periodically; do not treat disconnect as failure of the underlying workflow.
- Frontend: connect SSE and periodically refresh `GET /runs/{id}` at state transitions. If SSE unavailable, poll events every ~2 seconds with `after_seq`.
- Never stream raw LLM text or fake stages. Events are emitted by actual backend nodes.

## 7. UI pages and components

**Page A — `/upload`:** accessible PDF drop zone, validation feedback, submit button, and clear link to created run.

**Page B — `/runs/:id`:** two-column view: PDF preview with text-layer highlights/page evidence on left; live node timeline, extracted critical fields, checks, PO candidates, price variance, decision, review action and traceable reason on right. Include stage durations and measured OpenAI cost. For scanned PDFs show page-level evidence when bbox is unavailable; do not fake highlights.

**Page C — `/dashboard`:** run history filterable by status/decision; straight-through processing rate, pending review count, average processing duration, average estimated API cost, approved invoice value. Avoid calling rejected invoices "savings" unless a justified counterfactual exists.

**Page D (could be an inline panel):** reviewer question, PO choices, discrepancy evidence, mandatory reason and action submission. Changes to policy require an admin and create a new policy version, then explicit reevaluation.

## 8. UI state design

- `runsListQuery` for dashboard; `runQuery` for canonical state; `events` ordered by sequence; `reviewRequestQuery` only if `WAITING_REVIEW`.
- An event is append-only and deduplicated client-side by `seq`. On navigation or reconnect, first fetch stored events, then subscribe to SSE.
- Terminal `FAILED` shows a safe retry explanation. Terminal `REJECTED` shows a business-rule explanation and optional draft response. They must not share a generic red "Error" label.

## 9. Export format

Approved run -> CSV row with `invoice_id, invoice_number, vendor_id, po_number, currency, gross, decision_at, policy_version, run_id`. Never claim the file sent money or posted to an ERP. CSV export is a simulated AP handoff.

## 10. Explicit non-goals

No public document browsing, anonymous review, actual email send, payment API, real ERP integration, external inbound webhook, or automated account creation for v1.
