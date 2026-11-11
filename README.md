# PS-1 Invoice Automation — Day-0 Planning

**Canonical contract:** [`SPEC.md`](SPEC.md) (v0.2-draft, 2026-11-11).

This folder is an architecture-first planning deliverable, **not application source code**. `SPEC.md` combines requirements, schemas, typed financial rules, LangGraph workflow, API/SSE, demo fixtures, recovery/idempotency, and build milestones into a single authoritative contract.

The five older documents (`DATA_CONTRACTS.md`, `BUSINESS_RULES.md`, `WORKFLOW_DESIGN.md`, `API_CONTRACT.md`, `EVALUATION_PLAN.md`) are retained as **historical design notes**. Where they differ, use `SPEC.md` and update it alongside implementation changes.

**Fixed scope:** one OpenAI provider/API key; conservative deterministic approvals; human-in-the-loop via LangGraph; real live events; four meaningful demo edge cases; live hosted system; no payments or automatic email sends.

**Still to validate:** model and input path on invoice gold set, actual API costs, scanned extraction accuracy, final hosting/storage selection, and robustness in a deployed environment. The ₹2 arithmetic exception is an *explicit demonstration policy*, **not** an AP industry recommendation.
