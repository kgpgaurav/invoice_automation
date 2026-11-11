# Implementation decisions and unresolved questions

Read against SPEC.md v0.2-draft and AGENTS.md on 2026-11-11. Archived documents are not active contracts.

## Slice 1 boundary

Implement SPEC §§1.2, 3.1, 3.4, 4.1 and the initial upload shell from §4.3. This is local infrastructure and durable intake only. No extraction, worker, artificial stages, financial verdict, review, or payment export exists yet. A run remains QUEUED; decision is null. The UI explicitly discloses this. LangGraph is deferred until the financial commit contract and tests exist (§2.3).

## Local implementation choices

1. **PDF storage (§1.2): PostgreSQL BYTEA.** One transaction can persist PDF, run, queue entry, event and intake idempotency record. This is one of the spec's permitted options. Enforce the 12 MiB / five-page limits. Tradeoff: database size; move to private object storage only through an explicit later decision if necessary.
2. **Authentication (§4): temporary single-user bearer credential**, configured server-side and entered in the UI, held only in component memory. No credential is bundled in Vite or committed. Required for intake and run reads. This is a local scaffold, not a final deployed identity/role design. Deployment and review endpoints require a decision about reviewer/admin identity first.
3. **Health paths (§4.1): `/api/v1/healthz` and `/api/v1/readyz`**, following the stated base path. Liveness does not contact the database. Readiness checks connectivity and the exact Alembic head; it reports API/database readiness only, not worker/OpenAI readiness. Both are public and return sanitized errors. No automatic migrations on API startup.
4. **Intake idempotency:** optional header as specified. Scope is this single-user intake endpoint; fingerprint uses PDF bytes plus the optional source (filename is not business payload). Same key and fingerprint returns the original 202 resource; changed payload returns 409, including concurrent submissions. A new key can create another run; this is not canonical invoice duplicate approval protection. That belongs to §1.3/§2.3.
5. **Partial migration baseline:** create only documents, runs, run_events, run_queue and intake_keys. Future migrations add financial/review/policy tables alongside their tested slices. Stable run/thread UUIDs exist now. Unimplemented model/prompt/policy metadata is visibly `not-configured`, not a claim of a live extraction or active financial policy.

## Conflicts, gaps and blockers for later slices

- SPEC calls itself v0.2-draft but §5.4 asks to freeze a v1 baseline; this implementation does not relabel or freeze it. Kickoff criteria mix deployment, fixture and financial prerequisites with first infrastructure work. Local scaffolding can proceed without pretending these gates passed.
- AGENTS requires explicit agreement for changes to README/SPEC/contracts; SPEC §5.5 broadly says every implementation change updates SPEC. Follow the narrower rule: leave these files unchanged because no product contract is changed; put implementation status and commands in docs/DEVELOPMENT.md.
- Hosting, managed database provider, always-on worker behavior and deployed identity/roles remain unselected. They block deployment, not local scaffolding. The user-provided case-study PDF is absent from the active root; no independent assessment of that brief is claimed.
- OpenAI candidate IDs in §3.5 are unverified in the project's API account. Do not assume agent model labels are available API models. Model/account availability, input path, pricing and accuracy need the specified benchmark before extraction is enabled. No AI call occurs in this slice.
- §1.1 permits only INR/null in extraction while unsupported currency must trigger review. Define how original unsupported currency is preserved as evidence rather than lost during schema validation before extraction work.
- Line/tax evidence lacks explicit rate, tax basis and PO tax metadata needed to prove §2.2 tax consistency. H2 needs exact line totals, printed gross and tax convention; ₹2 alone does not prove a rounding exception. Confirm fixtures before rule implementation. Defaults are not altered.
- PO/vendor status vocabularies, inactive supplier outcomes, tax-ID jurisdiction normalization, PO period/timezone boundaries, quantities/unit-price decimal precision, and aggregate allocation when multiple invoice lines match one PO line need precise definitions before finance migrations/rules.
- Reviews need a closed action/payload schema, evidence correction provenance, authorization, request-info behavior, and review-generation/resume idempotency. Queue retry/lease/heartbeat bounds and checkpoint setup/versioning also need definition before a worker is enabled.
- Runs lack explicit columns for extraction/schema/input-path versions, canonical retry linkage and per-run policy snapshot despite narrative requirements. Add these with the relevant slice, documenting the proposed representation first. Run detail/pagination/error envelopes are only partially specified; this slice exposes a minimal typed status subset, not a full extraction response.
- No Git repository is initialized in this folder. Source files can be created and tested, but Git diff/commit checks are unavailable.

## Slice 2 contract proposal (recorded before implementation)

Scope: SPEC §§1.2, 3.1, 3.4, 4.1–4.2 and 5.5. No financial or existing HTTP contract changes. The spec omits queue statuses, fencing, retry limits and an event idempotency key; these are internal refinements proposed under the user's Slice 2 instruction.

- Queue READY → LEASED → DONE or FAILED; technical retries return to READY on the same run/thread/document. This distinguishes infrastructure retries from §1.2's new-run business re-evaluation. Defaults: lease 30s, heartbeat 10s, max 3 claims, retry delay 5/10/20s capped at 60s. DB clock controls eligibility/expiry. Attempts increment only on committed claims.
- Claim with SKIP LOCKED and hold a dedicated session advisory lock for the run until processing exits. Expired leases are recoverable only if that lock is free; a paused live owner cannot race a replacement. Attempt number and unique claim owner fence all writes. Session locks require a direct/session-pooled DB connection, not transaction pooling. A dead process releases its connection/lock; a live stuck process prioritizes safety over availability and needs termination.
- Claims and retries persist actual WORKER-stage lifecycle events using existing allowed event types. No extraction or approval events. Event sequence is allocated while holding the run row lock; a new nullable unique (run_id,event_key) deduplicates operation replay. Conflicting reuse fails and rolls back. Event reads use after_seq and bounded limit, returning the existing §4.2 envelope.
- Retry exhaustion is FAILED with null financial decision. A test processor's return only acknowledges queue work and leaves the run INTERRUPTED with TEST_PROCESSOR_ONLY; never COMPLETED or a business verdict. Test processors exist only in tests and are injected explicitly; the production CLI fails closed before claiming any job. No runtime arbitrary import/processor switch.
- No ledger/checkpoint tables exist yet. Recovery is deliberately restricted to this test-only infrastructure; a real processor must implement checkpoint/ledger reconciliation before activation. Exactly-once arbitrary computation/external side effects cannot be promised after a crash; this slice guarantees serialized ownership, fenced DB writes and idempotent committed events, not zero repeated computation.
- Migration adds only event deduplication and queue indexes. Existing intake and status schemas remain compatible. Frontend source stays unchanged; generated API schema/types include the planned events endpoint. SSE remains deferred.

Acceptance: all Slice 1 regressions; competing processes, killed owner and restart, live expired owner exclusion, heartbeat/fencing, retry exhaustion, duplicate/conflicting events, transaction rollback and concurrent intake. Implement in worker/events modules, migration 0002, API events route and focused integration tests.

The proposal is implemented as an internal refinement under the requested scope; SPEC financial rules and existing endpoint contracts are unchanged. Existing event type vocabulary is reused, with stage WORKER and explicit operation payloads. Polling clients can use the new planned endpoint without any UI changes. Production CLI exits 2 before loading settings or connecting. A processor crash may repeat uncommitted computation: processors must use fenced/idempotent effects. If a DB connection is lost while CPU work continues, session-lock exclusivity no longer covers that CPU work; lease/attempt checks reject stale DB writes after recovery. Arbitrary external side effects remain out of scope. PostgreSQL session locks follow the [official locking documentation](https://www.postgresql.org/docs/17/explicit-locking.html).

## Implementation order (remaining roadmap)

1. This slice: config, database migration/connectivity, health/readiness, bounded authenticated PDF intake, queued status UI and PostgreSQL tests.
2. Durable single-worker claiming/events/recovery with explicit stub labels; fixture definitions/reset; generated frontend types from OpenAPI (already used for the implemented subset).
3. Freeze financial schemas, tax/evidence and fixture choices; implement/test idempotent approval transaction, locking and concurrency invariants before graph nodes.
4. Time-box OpenAI benchmark; extraction Pydantic schema, evidence verification and measured usage; one real PDF.
5. LangGraph durable checkpoints, deterministic vendor/duplicate/PO/rules and side-effect-free review interrupt/resume; H1/E1/E2.
6. E3/E4, dashboard/SSE, exports, recovery/concurrency checks, hosting and repeated demo rehearsal. H2/highlights/policy editor follow the safety gates.
