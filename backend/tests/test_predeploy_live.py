"""One explicitly authorized BYOK invoice; never runs in routine regression."""

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.extraction_client import Rates, estimated_cost
from app.extraction_store import APIUsage
from app.financial_models import ApprovalLedger
from app.main import create_app
from app.models import Run
from app.provider_credentials import ReviewerWorkflowProcessor
from app.worker import Worker, WorkerPolicy
from scripts.demo_fixtures import dataset, seed
from tests.test_predeploy_endpoints import TOKENS


@pytest.mark.skipif(
    os.environ.get("PS1_LIVE_PREDEPLOY") != "1",
    reason="Explicit PS1_LIVE_PREDEPLOY=1 authorization required for one billable BYOK invoice",
)
def test_one_live_submitter_invoice_and_finance_read(workflow_db):
    local = dotenv_values(".env")
    key = os.environ.get("OPENAI_API_KEY") or local.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL") or local.get("OPENAI_MODEL")
    assert key and model, "Configure the key/model privately in backend/.env"
    settings = Settings(
        _env_file=None,
        database_url=workflow_db.url.render_as_string(hide_password=False),
        app_api_token=TOKENS["submitter"],
        reviewer_api_token=TOKENS["reviewer"],
        submitter_api_tokens={name: TOKENS[name] for name in ("submitter-b", "submitter-c")},
        access_mode="roles",
        openai_credential_mode="reviewer",
        byok_encryption_key=Fernet.generate_key().decode(),
    )
    seed(workflow_db)
    pdf = next(pdf for name, pdf, _ in dataset() if name == "H1")
    own = {"Authorization": "Bearer " + TOKENS["submitter"]}
    with TestClient(create_app(settings, workflow_db)) as client:
        connected = client.post("/api/v1/openai/sessions", headers=own, json={"api_key": key})
        assert connected.status_code == 200, connected.json().get("detail")
        assert model in connected.json()["models"], "Configured model is not offered for this key"
        capability = connected.json()["session_token"]
        headers = dict(own, **{"X-OpenAI-Session": capability, "X-Idempotency-Key": "one-live-h1"})
        submitted = client.post(
            "/api/v1/invoices/process",
            headers=headers,
            data={"model_id": model},
            files={"file": ("synthetic-h1.pdf", pdf, "application/pdf")},
        )
        assert submitted.status_code == 202
        run_id = submitted.json()["run_id"]
        # One claimed invoice, at most the existing two total Responses attempts.
        processor = ReviewerWorkflowProcessor(workflow_db, settings, "policy-1.1-demo")
        processor.check_ready()
        assert Worker(workflow_db, processor, WorkerPolicy(max_attempts=1)).run_once()
        result = client.get("/api/v1/runs/" + run_id, headers=own).json()
        finance = client.get(
            "/api/v1/runs/" + run_id,
            headers={"Authorization": "Bearer " + TOKENS["reviewer"]},
        )
        assert finance.status_code == 200
        assert (
            client.get(
                "/api/v1/runs/" + run_id,
                headers={"Authorization": "Bearer " + TOKENS["submitter-b"]},
            ).status_code
            == 404
        )
        client.delete("/api/v1/openai/session", headers=headers).raise_for_status()

    root = Path(__file__).resolve().parents[2]
    rate_table = json.loads((root / "docs/benchmarks/openai-rates-2026-11-12.json").read_text())
    quote = rate_table["models"].get(model)
    rates = None
    if quote:
        rates = Rates(
            *(Decimal(quote[name]) for name in ("input", "cached", "output")),
            cache_write=Decimal(quote["cache_write"]),
            source=rate_table["date"] + " " + quote["source"],
        )
    with Session(workflow_db) as session:
        usage = session.scalars(select(APIUsage).order_by(APIUsage.created_at)).all()
        attempts = []
        for row in usage:
            cost = estimated_cost(
                {
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "input_tokens_details": {
                        "cached_tokens": row.cached_tokens,
                        "cache_write_tokens": row.cache_write_tokens,
                    },
                },
                rates,
            )
            attempts.append(
                {
                    "model": row.model_id,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "cached_tokens": row.cached_tokens,
                    "cache_write_tokens": row.cache_write_tokens,
                    "latency_ms": row.latency_ms,
                    "error_code": row.error_code,
                    "dated_rate_estimate_usd": str(cost) if cost is not None else None,
                }
            )
        report = {
            "mode": "LIVE_OPENAI_BYOK_SYNTHETIC_H1",
            "invoice_count": session.scalar(select(func.count()).select_from(Run)),
            "model": model,
            "job_state": result["job_state"],
            "decision": result["decision"],
            "source_mode": result["source_mode"],
            "ledger_entries": session.scalar(select(func.count()).select_from(ApprovalLedger)),
            "attempts": attempts,
            "rate_source": rates.source if rates else None,
            "actual_billed_cost_usd": None,
        }
        target = root / ".local/predeploy/live-smoke.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    assert report["invoice_count"] == report["ledger_entries"] == 1
    assert 1 <= len(attempts) <= 2
    assert (result["job_state"], result["decision"], result["source_mode"]) == (
        "COMPLETED",
        "APPROVED",
        "LIVE_OPENAI",
    )
