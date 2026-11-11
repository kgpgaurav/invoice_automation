import json

import httpx

from app.extraction_schema import InvoiceExtractionV1
from app.pdf_input import inspect_pdf
from scripts.extraction_fixtures import fixture_set


def case(name="clean"):
    return next((pdf, expected) for ident, pdf, expected in fixture_set() if ident == name)


def untrusted_extraction(pdf, expected):
    from app.evidence_verification import labelled_records

    records = labelled_records(inspect_pdf(pdf).pages)
    data = dict(
        expected,
        evidence=[
            dict(field=key, raw_text=row, page=page, method="VISION")
            for key, matches in records.items()
            for page, row, _ in matches
        ],
    )
    return InvoiceExtractionV1.model_validate(data)


def response(extraction, usage=True):
    data = {
        "status": "completed",
        "model": "test-model",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": extraction.model_dump_json()}],
            }
        ],
    }
    if usage:
        data["usage"] = {
            "input_tokens": 100,
            "output_tokens": 50,
            "input_tokens_details": {"cached_tokens": 20},
        }
    return httpx.Response(200, json=data)


def payload(request):
    return json.loads(request.content)
