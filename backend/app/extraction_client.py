"""OpenAI Responses transport with no database dependencies or automatic financial decision."""

import base64
import json
import time
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.extraction_schema import (
    INSTRUCTIONS,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    InvoiceExtractionV1,
    output_format,
)
from app.pdf_input import inspect_pdf


class ExtractionError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Rates:
    input: Decimal
    cached: Decimal
    output: Decimal
    source: str
    cache_write: Decimal | None = None

    def __post_init__(self):
        for value in (self.input, self.cached, self.output, self.cache_write):
            if value is None:
                continue
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError("Token prices must be finite nonnegative Decimals")


def estimated_cost(usage, rates):
    if rates is None or not isinstance(usage, dict):
        return None
    if not isinstance(usage.get("input_tokens_details"), dict):
        return None
    tokens = (
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        usage.get("input_tokens_details", {}).get("cached_tokens"),
    )
    if any(type(t) is not int or t < 0 for t in tokens) or tokens[2] > tokens[0]:
        return None
    writes = usage["input_tokens_details"].get("cache_write_tokens", 0)
    if type(writes) is not int or writes < 0 or writes + tokens[2] > tokens[0]:
        return None
    if writes and rates.cache_write is None:
        return None
    return (
        (tokens[0] - tokens[2] - writes) * rates.input
        + tokens[2] * rates.cached
        + writes * (rates.cache_write or Decimal("0"))
        + tokens[1] * rates.output
    ) / Decimal("1000000")


class OpenAIExtractor:
    def __init__(self, key, model, client=None, sleep=time.sleep):
        if not key or not model:
            raise ExtractionError("OPENAI_CONFIGURATION_MISSING")
        self.model = model
        self.client = client or httpx.Client(
            base_url="https://api.openai.com/v1",
            timeout=45,
            headers={"Authorization": "Bearer " + key},
        )
        self.sleep = sleep

    def close(self):
        self.client.close()

    def available(self, model):
        try:
            result = self.client.get("/models/" + model)
            return result.status_code
        except httpx.HTTPError:
            raise ExtractionError("OPENAI_CONNECTION_ERROR") from None

    def extract(self, pdf, route="text", record=lambda _: None, rates=None):
        local = inspect_pdf(pdf, route)
        content = [{"type": "input_text", "text": local.text}]
        if route == "pdf":
            content = [
                {
                    "type": "input_file",
                    "filename": "invoice.pdf",
                    "file_data": "data:application/pdf;base64," + base64.b64encode(pdf).decode(),
                }
            ]
        repair = ""
        for attempt in range(2):
            started = time.monotonic()
            data, usage, code, result = {}, None, None, None
            retry = False
            try:
                response = self.client.post(
                    "/responses",
                    json={
                        "model": self.model,
                        "instructions": INSTRUCTIONS + repair,
                        "store": False,
                        "max_output_tokens": 10000,
                        "text": {"format": output_format()},
                        "input": [{"role": "user", "content": content}],
                    },
                )
                if response.status_code != 200:
                    retry = response.status_code == 429 or response.status_code >= 500
                    raise ExtractionError(f"OPENAI_HTTP_{response.status_code}")
                data = response.json()
                if not isinstance(data, dict):
                    data = {}
                    raise ExtractionError("OPENAI_RESPONSE_INVALID")
                usage = data.get("usage")
                if data.get("status") != "completed":
                    raise ExtractionError("OPENAI_INCOMPLETE")
                parts = [
                    part
                    for item in data.get("output", [])
                    if item.get("type") == "message"
                    for part in item.get("content", [])
                ]
                if any(p.get("type") == "refusal" for p in parts):
                    raise ExtractionError("OPENAI_REFUSAL")
                text = "".join(p.get("text", "") for p in parts if p.get("type") == "output_text")
                result = InvoiceExtractionV1.model_validate_json(text)
            except httpx.TransportError:
                code, retry = "OPENAI_TRANSIENT_ERROR", True
            except (ValidationError, json.JSONDecodeError, TypeError, AttributeError):
                code, retry = "EXTRACTION_SCHEMA_INVALID", True
                repair = (
                    "\nPrevious response violated the schema. Return required keys only; "
                    "no fabricated values."
                )
            except ExtractionError as error:
                code = error.code
            finally:
                cost = estimated_cost(usage, rates)
                record(
                    {
                        "attempt_id": str(uuid4()),
                        "attempt": attempt + 1,
                        "model_id": data.get("model")
                        if isinstance(data.get("model"), str)
                        else self.model,
                        "requested_model": self.model,
                        "usage": usage,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                        "prompt_version": PROMPT_VERSION,
                        "schema_version": SCHEMA_VERSION,
                        "input_path": route + ":" + local.path_version,
                        "estimated_cost_usd": str(cost) if cost is not None else None,
                        "rate_source": rates.source if rates else None,
                        "error_code": code,
                    }
                )
            if result is not None:
                return result
            if not retry or attempt == 1:
                raise ExtractionError(code or "EXTRACTION_FAILED")
            self.sleep(1)
