"""Explicit paid H1 smoke; synthetic masters and isolated PostgreSQL schemas only."""

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.extraction_client import OpenAIExtractor, Rates
from app.extraction_store import APIUsage
from app.financial_models import ApprovalLedger
from app.models import Run
from app.worker import Worker
from app.workflow import WorkflowProcessor
from tests.extraction_helpers import case
from tests.financial_fixtures import POLICY, masters
from tests.workflow_helpers import intake


@pytest.mark.skipif(
    os.environ.get("PS1_LIVE_WORKFLOW") != "1",
    reason="Set PS1_LIVE_WORKFLOW=1 explicitly to incur OpenAI API cost",
)
def test_live_h1_pdf_to_one_approval(workflow_db):
    engine = workflow_db
    config = dotenv_values(".env")
    key = os.environ.get("OPENAI_API_KEY") or config.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL") or config.get("OPENAI_MODEL")
    assert key and model, "Configure key/model locally; never in chat or source"
    root = Path(__file__).resolve().parents[2]
    rate_file = json.loads((root / "docs/benchmarks/openai-rates-2026-11-12.json").read_text())
    quote = rate_file["models"].get(model)
    rates = (
        Rates(
            *(Decimal(quote[k]) for k in ("input", "cached", "output")),
            source=rate_file["date"] + " " + quote["source"],
            cache_write=Decimal(quote["cache_write"]),
        )
        if quote
        else None
    )
    extractor = OpenAIExtractor(key, model)
    try:
        assert extractor.available(model) == 200
        masters(engine)
        pdf, _ = case()
        run_id = intake(engine, pdf)
        processor = WorkflowProcessor(engine, extractor, POLICY.version, rates=rates)
        processor.check_ready()
        assert Worker(engine, processor).run_once()
        with Session(engine) as s:
            run = s.get(Run, run_id)
            assert (run.job_state, run.decision) == ("COMPLETED", "APPROVED")
            assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
            usage = s.scalars(select(APIUsage)).all()
            report = {
                "mode": "LIVE_OPENAI_SYNTHETIC_H1",
                "model": model,
                "decision": run.decision,
                "ledger_entries": 1,
                "actual_billing_cost": None,
                "attempts": [
                    {
                        key: str(getattr(item, key)) if getattr(item, key) is not None else None
                        for key in (
                            "input_tokens",
                            "cached_tokens",
                            "cache_write_tokens",
                            "output_tokens",
                            "latency_ms",
                            "estimated_cost_usd",
                            "rate_source",
                            "error_code",
                        )
                    }
                    for item in usage
                ],
            }
            (root / ".local" / "slice5-live-h1.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(json.dumps(report))
    finally:
        extractor.close()
