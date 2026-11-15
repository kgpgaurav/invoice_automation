"""Durable invoice workflow. Checkpoints contain identifiers and routing codes only."""

from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langsmith import tracing_context
from sqlalchemy import func, select

from app.checkpoints import checkpoint_store
from app.events import append_event
from app.evidence_verification import VERIFIER_VERSION, verify
from app.extraction_client import ExtractionError
from app.extraction_schema import PROMPT_VERSION, SCHEMA_VERSION, InvoiceExtractionV1
from app.extraction_store import recorder
from app.finance_rules import resolve_vendor
from app.financial_models import PolicyVersion, PurchaseOrder, Vendor
from app.models import Document, QueueItem, Run
from app.owned_finalizer import finalize_owned
from app.ownership import owned_session
from app.workflow_models import ReviewAction, ReviewRequest, WorkflowRun

GRAPH_VERSION = "invoice-graph-1"


def check_workflow_infrastructure(engine, policy_version):
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        if session.get(PolicyVersion, policy_version) is None:
            raise ValueError("Register the immutable policy before enabling processing")
    with checkpoint_store(engine) as saver:
        version = saver.conn.execute(
            "SELECT max(v) AS version FROM checkpoint_migrations"
        ).fetchone()["version"]
        if version != len(saver.MIGRATIONS) - 1:
            raise ValueError("Run explicit checkpoint setup before enabling processing")


class InvoiceState(TypedDict, total=False):
    run_id: str
    generation: int
    decision: str
    code: str
    review_request_id: str
    action_id: str
    extraction_round: int
    review_options: list[str]
    review_kind: str


class WorkflowProcessor:
    durable_workflow = True

    def __init__(
        self,
        engine,
        extractor,
        policy_version,
        *,
        route="pdf",
        source_mode="LIVE_OPENAI",
        rates=None,
        crash_hook=lambda _: None,
        reservation_guard=lambda _: None,
    ):
        if source_mode not in ("LIVE_OPENAI", "MOCK_OPENAI") or route not in (
            "pdf",
            "text",
            "markdown",
        ):
            raise ValueError("Unsupported workflow configuration")
        self.engine, self.extractor, self.policy_version = engine, extractor, policy_version
        self.route, self.source_mode, self.rates = route, source_mode, rates
        self.crash_hook = crash_hook
        self.reservation_guard = reservation_guard

    def check_ready(self):
        check_workflow_infrastructure(self.engine, self.policy_version)
        if self.extractor.available(self.extractor.model) != 200:
            raise ValueError("Configured OpenAI model is unavailable; no jobs claimed")

    def __call__(self, worker, claim, pdf):
        def event(name, state, phase):
            with owned_session(worker, claim) as s:
                append_event(
                    s,
                    claim.run_id,
                    f"graph:{name}:{state.get('generation', 0)}:"
                    f"{state.get('extraction_round', 0)}:{phase}",
                    "STAGE_STARTED" if phase == "start" else "STAGE_FINISHED",
                    {"operation": name, "source": self.source_mode, "graph_version": GRAPH_VERSION},
                    stage=name,
                )

        def node(name, fn):
            def invoke(state):
                event(name, state, "start")
                output = fn(state)
                event(name, state, "end")
                return output

            return invoke

        def load(state):
            with owned_session(worker, claim) as s:
                run = s.get(Run, claim.run_id)
                if s.get(PolicyVersion, self.policy_version) is None:
                    raise ValueError("Register the immutable financial policy first")
                work = s.get(WorkflowRun, run.id)
                config = (
                    self.policy_version,
                    self.extractor.model,
                    PROMPT_VERSION,
                    SCHEMA_VERSION,
                    self.route,
                    self.source_mode,
                )
                if work is None:
                    s.add(
                        WorkflowRun(
                            run_id=run.id,
                            policy_version=config[0],
                            model_id=config[1],
                            prompt_version=config[2],
                            schema_version=config[3],
                            route=config[4],
                            source_mode=config[5],
                            graph_version=GRAPH_VERSION,
                            verifier_version=VERIFIER_VERSION,
                        )
                    )
                    run.policy_version, run.model_id, run.prompt_version = config[:3]
                elif (
                    work.policy_version,
                    work.model_id,
                    work.prompt_version,
                    work.schema_version,
                    work.route,
                    work.source_mode,
                ) != config:
                    raise ValueError("Workflow version/configuration changed during recovery")
            return {}

        def extract(state):
            with owned_session(worker, claim) as s:
                work = s.get(WorkflowRun, claim.run_id)
                remaining = 2 - work.extraction_attempts
                if work.extraction_json is not None and (
                    not state.get("extraction_round") or not remaining
                ):
                    append_event(
                        s,
                        claim.run_id,
                        "extraction-reused",
                        "STAGE_FINISHED",
                        {"operation": "PERSISTED_EXTRACTION_REUSED", "fresh_api_call": False},
                        stage="EXTRACTION",
                    )
                    return {}
                if not remaining:
                    if work.extraction_error not in (
                        "EXTRACTION_SCHEMA_INVALID",
                        "OPENAI_REFUSAL",
                        "OPENAI_INCOMPLETE",
                    ):
                        raise ExtractionError("EXTRACTION_ATTEMPTS_EXHAUSTED")
                    return {"code": work.extraction_error}

            def reserve(attempt_id):
                with owned_session(worker, claim) as s:
                    self.reservation_guard(s)
                    work = s.get(WorkflowRun, claim.run_id)
                    if work.extraction_attempts >= 2:
                        raise ExtractionError("EXTRACTION_ATTEMPTS_EXHAUSTED")
                    work.extraction_attempts += 1
                    append_event(
                        s,
                        claim.run_id,
                        f"api-start:{attempt_id}",
                        "STAGE_STARTED",
                        {
                            "operation": "OPENAI_REQUEST",
                            "source": self.source_mode,
                            "attempt_id": attempt_id,
                        },
                        stage="EXTRACTION",
                    )

            def record(attempt):
                with owned_session(worker, claim) as s:
                    run = s.get(Run, claim.run_id)
                    recorder(claim.connection, run.id, run.document_sha256)(attempt)

            try:
                extraction = self.extractor.extract(
                    pdf,
                    self.route,
                    record,
                    self.rates,
                    before_attempt=reserve,
                    max_attempts=remaining,
                    feedback=(
                        "\nCritical evidence was unresolved. Re-read missing critical values "
                        "and their exact page snippets; never invent or compute source values."
                        if state.get("extraction_round")
                        else None
                    ),
                )
            except ExtractionError as error:
                with owned_session(worker, claim) as s:
                    s.get(WorkflowRun, claim.run_id).extraction_error = error.code
                # Invalid content goes to review; transport/configuration failures remain technical.
                if error.code not in (
                    "EXTRACTION_SCHEMA_INVALID",
                    "OPENAI_REFUSAL",
                    "OPENAI_INCOMPLETE",
                ):
                    raise
                return {"code": error.code}
            with owned_session(worker, claim) as s:
                work = s.get(WorkflowRun, claim.run_id)
                work.extraction_json = extraction.model_dump(mode="json")
                work.extraction_history = work.extraction_history + [work.extraction_json]
                work.extraction_error = None
            return {}

        def evidence(state):
            with owned_session(worker, claim) as s:
                work = s.get(WorkflowRun, claim.run_id)
                wire = work.extraction_json
                attempts = work.extraction_attempts
            if wire:
                checked = verify(InvoiceExtractionV1.model_validate(wire), pdf)
                unresolved = set(checked.findings) & {
                    "CRITICAL_FIELD_MISSING",
                    "CRITICAL_LINE_FIELD_MISSING",
                    "UNVERIFIED_TOTAL",
                    "FINANCIAL_CONTRACT_INVALID",
                    "PRINTED_FIELD_OMITTED",
                }
                if unresolved and attempts < 2:
                    return {"code": "CRITICAL_SOURCE_RETRY", "extraction_round": 1}
            return {"code": ""}

        def match(state):
            result = finalize_owned(worker, claim, post=False)
            return {"decision": result.decision, "code": result.code}

        def finalize(state):
            self.crash_hook("before_financial_commit")
            result = finalize_owned(worker, claim)
            self.crash_hook("after_financial_commit")
            return {"decision": result.decision, "code": result.code}

        def prepare_review(state):
            generation = state["generation"] + 1
            with owned_session(worker, claim) as s:
                request = s.scalar(
                    select(ReviewRequest).where(
                        ReviewRequest.run_id == claim.run_id, ReviewRequest.generation == generation
                    )
                )
                work = s.get(WorkflowRun, claim.run_id)
                if request is None:
                    options = []
                    if state["code"] in ("PO_MISSING", "PO_AMBIGUOUS") and work.extraction_json:
                        run = s.get(Run, claim.run_id)
                        checked = verify(
                            InvoiceExtractionV1.model_validate(work.extraction_json),
                            s.get(Document, run.document_id).content,
                        )
                        if checked.document and checked.document.po_reference is None:
                            orders = s.scalars(select(PurchaseOrder)).all()
                            vendor, error = resolve_vendor(
                                checked.document, s.scalars(select(Vendor)).all(), orders
                            )
                            if vendor and error is None:
                                options = sorted(
                                    str(p.id)
                                    for p in orders
                                    if p.vendor_id == vendor.id and p.status == "OPEN"
                                )
                    request = ReviewRequest(
                        run_id=claim.run_id,
                        generation=generation,
                        kind="PO_SELECTION" if options else "EVIDENCE_OR_POLICY",
                        question=(s.get(Run, claim.run_id).reason or state["code"])
                        + ". "
                        + (
                            "Select an evidenced PO; all financial checks will run again."
                            if options
                            else "Reject or request corrected source information."
                        ),
                        options_json=options,
                    )
                    s.add(request)
                    s.flush()
                work.review_generation = generation
                return {
                    "generation": generation,
                    "review_request_id": str(request.id),
                    "review_options": request.options_json,
                    "review_kind": request.kind,
                }

        def request_review(state):
            # This node has no side effects before interrupt; it may restart verbatim.
            action_id = interrupt(
                {
                    "review_request_id": state["review_request_id"],
                    "generation": state["generation"],
                    "question": "Select a PO or stop for corrected source information.",
                    "options": state["review_options"],
                    "allowed_actions": (
                        ["SELECT_PO"] if state["review_kind"] == "PO_SELECTION" else []
                    )
                    + ["REJECT", "REQUEST_INFO"],
                }
            )
            return {"action_id": action_id}

        def apply_review(state):
            with owned_session(worker, claim) as s:
                request = s.get(ReviewRequest, UUID(state["review_request_id"]))
                action = s.get(ReviewAction, UUID(state["action_id"]))
                if (
                    request.run_id != claim.run_id
                    or request.status != "RESOLVED"
                    or action.review_request_id != request.id
                    or request.generation != state["generation"]
                ):
                    raise ValueError("Invalid durable review action")
            return {}

        graph = StateGraph(InvoiceState)
        for name, fn in (
            ("DOCUMENT_LOADING", load),
            ("EXTRACTION", extract),
            ("EVIDENCE_VERIFICATION", evidence),
            ("MATCHING", match),
            ("FINALIZATION", finalize),
            ("PREPARE_REVIEW", prepare_review),
            ("APPLY_REVIEW", apply_review),
        ):
            graph.add_node(name, node(name, fn))
        graph.add_node("HUMAN_REVIEW", request_review)
        graph.add_edge(START, "DOCUMENT_LOADING")
        for a, b in (
            ("DOCUMENT_LOADING", "EXTRACTION"),
            ("EXTRACTION", "EVIDENCE_VERIFICATION"),
            ("MATCHING", "FINALIZATION"),
            ("PREPARE_REVIEW", "HUMAN_REVIEW"),
            ("HUMAN_REVIEW", "APPLY_REVIEW"),
            ("APPLY_REVIEW", "MATCHING"),
        ):
            graph.add_edge(a, b)
        graph.add_conditional_edges(
            "EVIDENCE_VERIFICATION",
            lambda state: "EXTRACTION" if state["code"] == "CRITICAL_SOURCE_RETRY" else "MATCHING",
        )
        graph.add_conditional_edges(
            "FINALIZATION",
            lambda state: "PREPARE_REVIEW" if state["decision"] == "NEEDS_REVIEW" else END,
        )
        with owned_session(worker, claim) as s:
            run = s.get(Run, claim.run_id)
            work = s.get(WorkflowRun, claim.run_id)
            if work and (
                work.graph_version != GRAPH_VERSION or work.verifier_version != VERIFIER_VERSION
            ):
                raise ValueError("Graph/verifier version differs from the frozen run")
            if work and (
                work.policy_version,
                work.model_id,
                work.prompt_version,
                work.schema_version,
                work.route,
                work.source_mode,
            ) != (
                self.policy_version,
                self.extractor.model,
                PROMPT_VERSION,
                SCHEMA_VERSION,
                self.route,
                self.source_mode,
            ):
                raise ValueError("Workflow configuration differs from the frozen run")
            config = {"configurable": {"thread_id": str(run.thread_id)}}
            job_type = s.get(QueueItem, claim.job_id).work_type
        with checkpoint_store(self.engine, worker, claim) as saver, tracing_context(enabled=False):
            compiled = graph.compile(checkpointer=saver)
            snapshot = compiled.get_state(config)
            suspended = any(task.interrupts for task in snapshot.tasks)
            if job_type == "RESUME" and suspended:
                with owned_session(worker, claim) as s:
                    action = s.scalar(
                        select(ReviewAction).where(
                            ReviewAction.review_request_id
                            == UUID(snapshot.values["review_request_id"])
                        )
                    )
                    if action is None:
                        raise ValueError("Resume has no persisted review action")
                    value = Command(resume=str(action.id))
            elif not snapshot.values:
                value = {"run_id": str(claim.run_id), "generation": 0}
            else:
                value = None
            if snapshot.next or not snapshot.values:
                compiled.invoke(value, config, durability="sync")
            snapshot = compiled.get_state(config)
            suspended = any(task.interrupts for task in snapshot.tasks)
            if suspended:
                self.crash_hook("after_interrupt_checkpoint")
            with owned_session(worker, claim) as s:
                run = s.get(Run, claim.run_id)
                if suspended:
                    request = s.get(ReviewRequest, UUID(snapshot.values["review_request_id"]))
                    if request.status not in ("PREPARED", "OPEN"):
                        raise ValueError("Cannot park a resolved review")
                    request.status = "OPEN"
                    run.job_state, run.decision = "WAITING_REVIEW", "NEEDS_REVIEW"
                    run.reason = request.question
                    append_event(
                        s,
                        run.id,
                        f"review-requested:{request.id}",
                        "REVIEW_REQUESTED",
                        {"review_request_id": str(request.id), "generation": request.generation},
                        stage="HUMAN_REVIEW",
                    )
                elif snapshot.next:
                    raise ValueError("Workflow did not finish or interrupt")
                else:
                    completed = run.job_state == "COMPLETED"
                    append_event(
                        s,
                        run.id,
                        "workflow-completed" if completed else "workflow-stopped",
                        "RUN_COMPLETED" if completed else "STAGE_FINISHED",
                        {"decision": run.decision, "code": snapshot.values.get("code")},
                        stage="FINALIZATION",
                    )
                run.updated_at = func.now()
                job = s.get(QueueItem, claim.job_id)
                job.status, job.lease_until, job.claimed_by = "DONE", None, None
