"""Transport-size profiles; no extraction calls or financial decisions."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.contracts import MAX_PDF_BYTES
from app.main import create_app
from app.models import Document, Run


@pytest.mark.parametrize("mib", [4, 12])
def test_advertised_limit_matches_exact_intake_boundary(database, settings, pdf, mib):
    limit = mib * 1048576
    configured = Settings(_env_file=None, **(settings.model_dump() | {"max_pdf_bytes": limit}))
    original_xref = re.search(rb"startxref\s+(\d+)\s+%%EOF", pdf).group(1)
    end = b"\nstartxref\n" + original_xref + b"\n%%EOF\n"
    bounded_pdf = pdf + b" " * (limit - len(pdf) - len(end)) + end
    assert len(bounded_pdf) == limit
    with TestClient(create_app(configured, database[0])) as client:
        config = client.get("/api/v1/openai/config").json()
        assert (config["max_pdf_bytes"], config["max_pdf_pages"]) == (limit, 5)
        headers = {"Authorization": "Bearer " + settings.app_api_token.get_secret_value()}
        too_large = client.post(
            "/api/v1/invoices/process",
            headers=headers,
            files={"file": ("over.pdf", bounded_pdf + b" ", "application/pdf")},
        )
        assert too_large.status_code == 413
        assert f"{mib} MiB" in too_large.json()["detail"]["message"]
        with Session(database[0]) as session:
            assert session.scalar(select(func.count()).select_from(Run)) == 0
        accepted = client.post(
            "/api/v1/invoices/process",
            headers=headers,
            files={"file": ("boundary.pdf", bounded_pdf, "application/pdf")},
        )
        assert accepted.status_code == 202
        with Session(database[0]) as session:
            assert session.scalar(select(func.count()).select_from(Run)) == 1
            assert len(session.scalar(select(Document.content))) == limit


@pytest.mark.parametrize("invalid", [0, MAX_PDF_BYTES + 1])
def test_upload_profile_cannot_exceed_database_ceiling(settings, invalid):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **(settings.model_dump() | {"max_pdf_bytes": invalid}))
