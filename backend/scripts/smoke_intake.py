"""Exercise a running Vite proxy and API with synthetic, non-financial PDF data."""

import argparse
from uuid import uuid4

import httpx
import pymupdf

from app.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument("--origin", default="http://127.0.0.1:5173")
args = parser.parse_args()
settings = Settings()

with pymupdf.open() as document:
    document.new_page().insert_text(
        (72, 72), "Synthetic infrastructure smoke test. No invoice data."
    )
    content = document.tobytes()

with httpx.Client(base_url=args.origin, timeout=15) as client:
    page = client.get("/")
    page.raise_for_status()
    assert 'id="root"' in page.text
    assert client.get("/src/main.tsx").status_code == 200
    assert client.get("/api/v1/healthz").json()["status"] == "ok"
    assert client.get("/api/v1/readyz").json()["status"] == "ready"
    headers = {
        "Authorization": f"Bearer {settings.app_api_token.get_secret_value()}",
        "X-Idempotency-Key": f"smoke-{uuid4()}",
    }
    response = client.post(
        "/api/v1/invoices/process",
        headers=headers,
        files={"file": ("synthetic-smoke.pdf", content, "application/pdf")},
    )
    assert response.status_code == 202, response.text
    result = response.json()
    status = client.get(result["links"]["status"], headers=headers)
    status.raise_for_status()
    assert status.json()["job_state"] == "QUEUED"
    assert status.json()["decision"] is None
    assert "no worker" in status.json()["implementation_notice"]
    print(
        "PASS: Vite page/assets, proxied health/readiness, PDF intake and persisted queued status."
    )
    print(f"Synthetic queued run retained: {result['run_id']}")
