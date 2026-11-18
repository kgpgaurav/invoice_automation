"""All implemented operations in the three-submitter BYOK profile; no live HTTP provider."""

import base64
import hashlib
import json
import os
import runpy
from functools import partial
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import provider_routes, workflow
from app.config import Settings
from app.financial_models import ApprovalLedger, PurchaseOrder, Vendor
from app.main import create_app
from app.models import Run
from app.provider_credentials import ReviewerWorkflowProcessor, create_provider_session
from app.worker import Worker
from scripts.demo_fixtures import dataset, seed
from tests.extraction_helpers import response, untrusted_extraction

TOKENS = {
    name: f"synthetic-predeploy-{name}-access-at-least-24"
    for name in ("submitter", "submitter-b", "submitter-c", "reviewer")
}
KEYS = {name: f"synthetic-{name}-openai-key-never-live" for name in TOKENS if name != "reviewer"}
MODELS = {"submitter": "gpt-6-luna", "submitter-b": "gpt-6.1-terra", "submitter-c": "gpt-6-luna"}


def test_vercel_entrypoint_requires_private_profile_and_worker_is_disabled(database, monkeypatch):
    from app import config

    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "vercel.json").read_text())
    worker = manifest["daemons"]["invoice-worker"]
    assert sum(worker["instances"].values()) == 0
    assert worker["command"] == ["python", "-m", "scripts.hosted", "worker"]
    assert worker["resources"]["requests"]["memory"] == "1Gi"
    assert "env" not in manifest and "build" not in manifest
    assert "OPENAI_API_KEY" not in json.dumps(manifest)
    with database[0].connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    configured = Settings(
        _env_file=None,
        database_url=database[0].url.render_as_string(hide_password=False),
        database_schema=schema,
        app_api_token=TOKENS["submitter"],
        reviewer_api_token=TOKENS["reviewer"],
        submitter_api_tokens={name: TOKENS[name] for name in ("submitter-b", "submitter-c")},
        access_mode="roles",
        openai_credential_mode="reviewer",
        byok_encryption_key=Fernet.generate_key().decode(),
    )
    monkeypatch.setattr(config, "Settings", lambda: configured)
    entry = runpy.run_path(str(root / "backend/vercel_app.py"))
    with TestClient(entry["app"]) as client:
        assert client.get("/api/v1/readyz").status_code == 200
        assert client.get("/api/v1/openai/config").json()["max_pdf_bytes"] == 4 * 1048576
        oversized = client.post(
            "/api/v1/invoices/process",
            headers={"Authorization": "Bearer " + TOKENS["submitter"]},
            files={"file": ("over.pdf", b"%PDF-" + b" " * (4 * 1048576), "application/pdf")},
        )
        assert oversized.status_code == 413
        for actor, token in TOKENS.items():
            result = client.get("/api/v1/access", headers={"Authorization": "Bearer " + token})
            assert result.status_code == 200 and result.json()["actor_id"] == actor
    for overrides in (
        {"access_mode": "shared"},
        {"openai_credential_mode": "server"},
        {"reviewer_api_token": None},
        {"submitter_api_tokens": {}},
        {"openai_api_key": "synthetic-operator-key-must-not-be-deployed"},
    ):
        values = configured.model_dump() | overrides
        with pytest.raises(ValueError, match="Vercel demo requires"):
            entry["build_app"](Settings(_env_file=None, **values))


def test_all_operations_with_three_submitters_and_financial_review(workflow_db, monkeypatch):
    engine = workflow_db
    seed(engine)
    settings = Settings(
        _env_file=None,
        database_url=engine.url.render_as_string(hide_password=False),
        app_api_token=TOKENS["submitter"],
        reviewer_api_token=TOKENS["reviewer"],
        submitter_api_tokens={name: TOKENS[name] for name in ("submitter-b", "submitter-c")},
        access_mode="roles",
        openai_credential_mode="reviewer",
        byok_encryption_key=Fernet.generate_key().decode(),
    )

    def catalog(engine, settings, key, **kwargs):
        assert key in KEYS.values()
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"data": [{"id": m} for m in set(MODELS.values())]}
                )
            )
        ) as mocked:
            return create_provider_session(engine, settings, key, client=mocked, **kwargs)

    monkeypatch.setattr(provider_routes, "create_provider_session", catalog)
    # Only test provenance changes; the normal SessionExtractor and owned financial path run.
    monkeypatch.setattr(
        workflow,
        "WorkflowProcessor",
        partial(workflow.WorkflowProcessor, source_mode="MOCK_OPENAI"),
    )
    fixtures = {name: (pdf, expected) for name, pdf, expected in dataset()}
    by_hash = {hashlib.sha256(pdf).hexdigest(): expected for pdf, expected in fixtures.values()}
    calls = []

    def factory(key, model):
        assert key in KEYS.values()

        def handle(request):
            body = json.loads(request.content)
            assert body["model"] == model
            encoded = body["input"][0]["content"][0]["file_data"]
            pdf = base64.b64decode(encoded.split(",", 1)[1])
            calls.append((key, model))
            payload = response(
                untrusted_extraction(pdf, by_hash[hashlib.sha256(pdf).hexdigest()])
            ).json()
            payload["model"] = model
            return httpx.Response(200, json=payload)

        return httpx.Client(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle)
        )

    processor = ReviewerWorkflowProcessor(
        engine, settings, "policy-1.1-demo", client_factory=factory
    )
    processor.check_ready()
    app = create_app(settings, engine)
    observed, results = set(), []
    actors = [None, *TOKENS]
    with TestClient(app) as client:

        def probe(method, template, actor, expected, *, values=None, **kwargs):
            headers = kwargs.pop("headers", {})
            if actor is not None:
                headers = dict(headers, Authorization="Bearer " + TOKENS[actor])
            reply = client.request(
                method, "/api/v1" + template.format(**(values or {})), headers=headers, **kwargs
            )
            assert reply.status_code == expected, (method, template, actor, reply.status_code)
            observed.add((method.lower(), "/api/v1" + template))
            results.append(
                {
                    "method": method,
                    "path": template,
                    "actor": actor or "anonymous",
                    "status": expected,
                }
            )
            return reply

        for path in ("/healthz", "/readyz", "/openai/config", "/demo-access"):
            for actor in actors:
                probe("GET", path, actor, 200)
        for actor in actors:
            result = probe("GET", "/access", actor, 401 if actor is None else 200)
            if actor:
                assert result.json()["actor_id"] == actor

        with Session(engine) as session:
            vendor_id = str(
                session.scalar(
                    select(Vendor.id).where(Vendor.legal_name == "Aster Office Supplies")
                )
            )
        order_body = dict(
            po_number="PO-MATRIX-CREATED",
            vendor_id=vendor_id,
            currency="INR",
            issued_at="2026-10-01",
            cap_gross="11800",
            reason="Synthetic endpoint coverage authorization.",
            lines=[
                dict(
                    description="Office paper",
                    sku="PAPER",
                    quantity="10",
                    unit_price="1000",
                    tax_rate="18",
                )
            ],
        )
        for actor in actors:
            expected = 401 if actor is None else 200 if actor == "reviewer" else 403
            probe("GET", "/vendors", actor, expected)
            vendor_result = probe(
                "POST",
                "/vendors",
                actor,
                401 if actor is None else 201 if actor == "reviewer" else 403,
                headers={"X-Idempotency-Key": "matrix-vendor-create"},
                json={
                    "legal_name": "Endpoint matrix vendor",
                    "status": "INACTIVE",
                    "reason": "Synthetic vendor registration coverage.",
                },
            )
            if actor == "reviewer":
                new_vendor_id = vendor_result.json()["vendor_id"]
            probe(
                "POST",
                "/purchase-orders/preview",
                actor,
                expected,
                json={"lines": order_body["lines"]},
            )
            probe(
                "POST",
                "/purchase-orders",
                actor,
                401 if actor is None else 201 if actor == "reviewer" else 403,
                headers={"X-Idempotency-Key": "matrix-po-create"},
                json=order_body,
            )
        for actor in actors:
            probe(
                "PATCH",
                "/vendors/{vendor_id}/status",
                actor,
                401 if actor is None else 200 if actor == "reviewer" else 403,
                values={"vendor_id": new_vendor_id},
                headers={"X-Idempotency-Key": "matrix-vendor-status"},
                json={"status": "BLACKLISTED", "reason": "Synthetic status coverage."},
            )

        connections = {}
        for actor in actors:
            result = probe(
                "POST",
                "/openai/sessions",
                actor,
                401 if actor is None else 403 if actor == "reviewer" else 200,
                json={"api_key": KEYS.get(actor, "synthetic-denied-key")},
            )
            if actor in KEYS:
                assert result.headers["cache-control"] == "no-store"
                assert KEYS[actor] not in result.text
                connections[actor] = result.json()["session_token"]

        runs = {}

        def intake(actor, fixture, key):
            return probe(
                "POST",
                "/invoices/process",
                actor,
                202,
                headers={"X-OpenAI-Session": connections[actor], "X-Idempotency-Key": key},
                data={"model_id": MODELS[actor]},
                files={"file": ("synthetic.pdf", fixtures[fixture][0], "application/pdf")},
            ).json()["run_id"]

        for actor in (None, "reviewer"):
            probe(
                "POST",
                "/invoices/process",
                actor,
                401 if actor is None else 403,
                files={"file": ("synthetic.pdf", fixtures["H1"][0], "application/pdf")},
            )
        for actor, fixture in zip(KEYS, ("H1", "E2", "E4"), strict=True):
            runs[actor] = intake(actor, fixture, "same-intake-key")
            assert intake(actor, fixture, "same-intake-key") == runs[actor]
            assert Worker(engine, processor).run_once()
        assert calls == [(KEYS[actor], MODELS[actor]) for actor in KEYS]

        with Session(engine) as session:
            po_id = str(
                session.scalar(
                    select(PurchaseOrder.id).where(PurchaseOrder.po_number == "PO-SELECT-001")
                )
            )
        for actor in actors:
            valid = actor is not None
            run_id = runs.get(actor, runs["submitter-b"])
            for path in (
                "/runs/{run_id}",
                "/runs/{run_id}/document",
                "/runs/{run_id}/events",
                "/runs/{run_id}/events/stream",
            ):
                result = probe("GET", path, actor, 200 if valid else 401, values={"run_id": run_id})
                if valid and path == "/runs/{run_id}":
                    assert result.json()["source_mode"] == "MOCK_OPENAI"
                    if actor != "reviewer":
                        assert "purchase_order" not in result.json()
                if valid and path.endswith("/document"):
                    assert result.content.startswith(b"%PDF-")
                    assert result.headers["cache-control"] == "no-store"
                if valid and path.endswith("/stream"):
                    ids = [
                        int(line[4:])
                        for line in result.text.splitlines()
                        if line.startswith("id: ")
                    ]
                    assert ids and ids == sorted(set(ids))
            result = probe("GET", "/runs", actor, 200 if valid else 401)
            if valid:
                assert result.json()["total_count"] == (3 if actor == "reviewer" else 1)
            for path, values in (
                ("/purchase-orders", {}),
                ("/purchase-orders/{po_id}", {"po_id": po_id}),
                ("/dashboard/summary", {}),
                ("/runs/{run_id}/review", {"run_id": runs["submitter-b"]}),
            ):
                probe(
                    "GET",
                    path,
                    actor,
                    401 if not valid else 200 if actor == "reviewer" else 403,
                    values=values,
                )

        for actor, own in runs.items():
            for foreign in runs.values():
                if foreign != own:
                    for suffix in ("", "/document", "/events", "/events/stream"):
                        probe(
                            "GET", "/runs/{run_id}" + suffix, actor, 404, values={"run_id": foreign}
                        )

        review = client.get(
            "/api/v1/runs/" + runs["submitter-b"] + "/review",
            headers={"Authorization": "Bearer " + TOKENS["reviewer"]},
        ).json()
        body = {
            "generation": review["generation"],
            "action": "SELECT_PO",
            "payload": {"po_id": po_id},
            "reason": "Verified synthetic supporting procurement record.",
        }
        for actor in actors:
            accepted = probe(
                "POST",
                "/reviews/{review_id}/respond",
                actor,
                202 if actor == "reviewer" else 403,
                values={"review_id": review["review_request_id"]},
                json=body,
                headers={"X-Idempotency-Key": "same-review-action"},
            )
        replay = probe(
            "POST",
            "/reviews/{review_id}/respond",
            "reviewer",
            202,
            values={"review_id": review["review_request_id"]},
            json=body,
            headers={"X-Idempotency-Key": "same-review-action"},
        )
        assert replay.json() == accepted.json()
        # Revocation does not prevent financial review/resume of already persisted extraction.
        probe(
            "DELETE",
            "/openai/session",
            "submitter-b",
            204,
            headers={"X-OpenAI-Session": connections["submitter-b"]},
        )
        assert Worker(engine, processor).run_once()
        assert len(calls) == 3
        assert (
            client.get(
                "/api/v1/runs/" + runs["submitter-b"],
                headers={"Authorization": "Bearer " + TOKENS["submitter-b"]},
            ).json()["decision"]
            == "APPROVED"
        )

        def resolve(run_id, action):
            review = client.get(
                "/api/v1/runs/" + run_id + "/review",
                headers={"Authorization": "Bearer " + TOKENS["reviewer"]},
            ).json()
            probe(
                "POST",
                "/reviews/{review_id}/respond",
                "reviewer",
                202,
                values={"review_id": review["review_request_id"]},
                headers={"X-Idempotency-Key": "resolve-" + action},
                json={
                    "generation": review["generation"],
                    "action": action,
                    "payload": {},
                    "reason": "Synthetic predeployment action; no payment.",
                },
            )
            assert Worker(engine, processor).run_once()

        resolve(runs["submitter-c"], "REQUEST_INFO")
        scan = intake("submitter-c", "E3-scan", "scan-review")
        assert Worker(engine, processor).run_once()
        resolve(scan, "REJECT")
        with Session(engine) as session:
            assert session.get(Run, UUID(runs["submitter-c"])).job_state == "INTERRUPTED"
            assert session.get(Run, UUID(scan)).decision == "REJECTED"
            assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 2

        for actor in actors:
            result = probe(
                "DELETE",
                "/openai/session",
                actor,
                401 if actor is None else 403 if actor == "reviewer" else 204,
                headers={"X-OpenAI-Session": connections.get(actor, connections["submitter"])},
            )
            if actor in KEYS:
                assert result.headers["cache-control"] == "no-store"

        implemented = {
            (method, path)
            for path, methods in app.openapi()["paths"].items()
            for method in methods
            if method in {"get", "post", "delete", "put", "patch"}
        }
        assert observed == implemented
        assert len(implemented) == 23
        for method, path in (
            ("GET", "/policies/current"),
            ("POST", "/policies"),
            ("POST", "/runs/" + runs["submitter"] + "/reevaluate"),
            ("GET", "/runs/" + runs["submitter"] + "/export"),
        ):
            assert (
                client.request(
                    method,
                    "/api/v1" + path,
                    headers={"Authorization": "Bearer " + TOKENS["reviewer"]},
                ).status_code
                == 404
            )

    if filename := os.environ.get("PS1_PREDEPLOY_REPORT"):
        root = Path(__file__).resolve().parents[2]
        target = (root / filename).resolve()
        assert target.is_relative_to(root / ".local")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"mode": "MOCK_OPENAI", "operations": len(observed), "probes": results}, indent=2
            ),
            encoding="utf-8",
        )
