"""Explicit opt-in only; never spend on routine regression tests."""

import os

import pytest

from app.extraction_client import OpenAIExtractor
from tests.extraction_helpers import case


@pytest.mark.skipif(
    os.environ.get("PS1_LIVE_EXTRACTION") != "1",
    reason="Set PS1_LIVE_EXTRACTION=1 explicitly to incur OpenAI API cost",
)
def test_live_controlled_pdf_extracts_without_financial_commit():
    from dotenv import dotenv_values

    values = dotenv_values(".env")
    key = os.environ.get("OPENAI_API_KEY") or values.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL") or values.get("OPENAI_MODEL")
    assert key and model, "Configure API key/model locally; never put secrets in test files"
    client = OpenAIExtractor(key, model)
    pdf, expected = case()
    attempts = []
    try:
        actual = client.extract(pdf, "pdf", attempts.append)
        assert actual.invoice_number == expected["invoice_number"]
        assert actual.total_gross == expected["total_gross"]
        assert attempts and attempts[-1]["usage"] is not None
    finally:
        client.close()
