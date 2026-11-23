"""Strict field-only repair; the model cannot change other values or trusted state."""

import re

from pydantic import create_model

from app.extraction_schema import FieldEvidenceV1, InvoiceExtractionV12, InvoiceLineV12, WireModel


def repair_model(previous, fields):
    if not fields or len(set(fields)) != len(fields):
        raise ValueError("Repair requires unique field paths")
    definitions = {}
    for path in fields:
        match = re.fullmatch(r"lines\.([1-9][0-9]*)\.([a-z_]+)", path)
        if match:
            position, name = int(match[1]), match[2]
            if position > len(previous.line_items) or name == "line_no":
                raise ValueError("Repair cannot change row identity")
            source = type(previous.line_items[position - 1]).model_fields
        else:
            name, source = path, type(previous).model_fields
            if name in ("line_items", "evidence"):
                raise ValueError("Repair cannot replace rows or evidence wholesale")
        if name not in source:
            raise ValueError("Unsupported repair field")
        definitions[path] = (source[name].annotation, ...)
    values = create_model("InvoiceRepairValuesV1", __base__=WireModel, **definitions)
    return create_model(
        "InvoiceRepairV1",
        __base__=WireModel,
        values=(values, ...),
        evidence=(list[FieldEvidenceV1], ...),
    )


def merge_repair(previous, repair, fields):
    data = previous.model_dump()
    line_numbers = [line.line_no for line in previous.line_items]

    def citation_path(path):
        if not path.startswith("lines."):
            return path
        _, position, name = path.split(".")
        printed = line_numbers[int(position) - 1]
        label = printed if printed is not None and line_numbers.count(printed) == 1 else position
        return f"lines.{label}.{name}"

    values = repair.values.model_dump()
    if set(values) != set(fields) or any(e.field not in fields for e in repair.evidence):
        raise ValueError("Repair changed unrequested fields")
    for path, value in values.items():
        if path.startswith("lines."):
            _, position, name = path.split(".")
            data["line_items"][int(position) - 1][name] = value
        else:
            data[path] = value
    replaced = {citation_path(path) for path in fields}
    data["evidence"] = [e for e in data["evidence"] if e["field"] not in replaced] + [
        dict(e.model_dump(), field=citation_path(e.field)) for e in repair.evidence
    ]
    return type(previous).model_validate(data)


def schema_issues(error):
    """Do not persist Pydantic input/context/messages or arbitrary extra-property names."""
    allowed = (
        set(InvoiceExtractionV12.model_fields)
        | set(InvoiceLineV12.model_fields)
        | {
            "field",
            "raw_text",
            "page",
            "method",
            "values",
        }
    )
    return [
        {
            "path": ".".join(
                str(p) if isinstance(p, int) or p in allowed else "?" for p in issue["loc"]
            ),
            "code": issue["type"],
        }
        for issue in error.errors(include_input=False, include_context=False, include_url=False)[
            :100
        ]
    ]
