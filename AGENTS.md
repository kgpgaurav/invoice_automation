# Codex instructions — PS-1 Invoice-to-Decision Automation

## Source of truth
- Read `SPEC.md` fully before writing or modifying code. `SPEC.md` is the canonical product, data, workflow, API, and test contract; older design docs are historical notes only.
- Read `README.md` to understand what is implemented vs. only planned. The current SPEC is a draft, not evidence that code exists or has been tested.
- If the spec is ambiguous, record the proposed decision and its tradeoffs in `docs/DECISIONS.md` before building a nontrivial feature. Do not silently change financial policy or API contracts.

## Mission and scope
- Implement a **real**, live, testable invoice-PDF-to-decision workflow for the PS-1 case study, with a clean upload UI, stage-by-stage run timeline, dashboard/history, readable decision reasons, and meaningful exception handling.
- Use only OpenAI as the AI provider. One application API key; do not require other LLM providers. Do not claim any selected model is the cheapest or most accurate until measured on fixtures.
- Use FastAPI, Pydantic, PostgreSQL/SQLAlchemy, LangGraph with durable checkpoints and human-review interrupts, React/TypeScript, and deterministic Python business rules, as scoped by `SPEC.md`.
- The LLM extracts document fields; it never determines final financial authorization. Never execute real payments or automatically send vendor emails.

## Financial correctness / reliability
- Money uses `Decimal` and explicit currency units; no float arithmetic.
- Missing or ambiguous critical evidence, mismatched vendors or POs, tax inconsistencies, and excess PO spend must never be silently auto-approved.
- Keep typed tolerances separate (arithmetic rounding, unit price, tax, PO balance); defaults are per `SPEC.md`.
- Prevent duplicate approvals atomically. Recheck PO balance with row locking in the same transaction as the invoice ledger/approval update.
- Keep the `interrupt()` call in a side-effect-free review node; after resume, re-evaluate current financial data. Checkpoint IDs/thread IDs must be stable.
- Run creation, retries, replay, and crash recovery must be idempotent. Clearly label fixture or replayed LLM data; never masquerade it as a fresh live model call.
- Secrets must stay in environment variables or ignored `.env` files. Never commit API keys, invoice banking secrets, or production credentials.

## Working protocol
1. At the beginning of each task, identify the precise spec section and summarize expected file edits and acceptance tests.
2. Implement **one small vertical slice at a time**. Do not implement the entire seven-day roadmap from one broad prompt.
3. Run relevant tests and inspect errors before declaring the slice complete. Report which commands were run and which failed.
4. Do not add Redis, vector databases, multiple AI providers, complex agent swarms, payment execution, or email delivery without a new explicit project decision.
5. For a stub/walking skeleton, clearly mark stub outputs and never present it as working AI extraction.
6. Update `README.md`, API contracts, and `SPEC.md` if and only if there is an explicit agreed contract change.

## Initial implementation slice
- First inspect `SPEC.md` and summarize any conflicting/ambiguous choices.
- Then establish folder structure, env example, Python backend skeleton, React/Vite frontend skeleton, database connectivity/migration baseline, health endpoint, and a basic upload/run-status flow that can be exercised locally.
- Keep artificial processing events clearly labeled as demonstration stubs. Stop after showing the slice, tests, and next recommended milestone.
