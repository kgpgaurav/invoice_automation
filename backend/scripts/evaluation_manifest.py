"""Load privately supplied gold labels; never infer truth from model output."""

import json
from pathlib import Path


def load_cases(path):
    path = Path(path).resolve()
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries:
        raise ValueError("Evaluation manifest must be a nonempty list")
    result, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid evaluation case")
        ident, source, expected = (
            entry.get(k)
            for k in (
                "fixture_id",
                "source_pdf",
                "expected_fields",
            )
        )
        grounding = entry.get("expected_grounding", {})
        if (
            not isinstance(ident, str)
            or not ident
            or ident in seen
            or not isinstance(source, str)
            or not isinstance(expected, dict)
            or not expected
            or not isinstance(grounding, dict)
            or any(not isinstance(k, str) or type(v) is not bool for k, v in grounding.items())
        ):
            raise ValueError(
                "Evaluation cases require unique IDs, PDF paths and independent labels"
            )
        seen.add(ident)
        content = (path.parent / source).read_bytes()
        result.append((ident, content, expected, grounding))
    return result
