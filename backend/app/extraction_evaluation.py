"""Measured field scores; schema validity alone is never an accuracy metric."""

from decimal import Decimal, InvalidOperation


def flatten(data, prefix=""):
    result = {}
    for key, value in data.items():
        if key == "evidence":
            continue
        path = prefix + key
        if isinstance(value, list):
            result[path + ".count"] = len(value)
            for i, line in enumerate(value):
                result.update(flatten(line, path + f".{i}."))
        else:
            result[path] = value
    return result


def field_metrics(expected, actual):
    truth, predicted = flatten(expected), flatten(actual)
    available = {
        k: v
        for k, v in truth.items()
        if not k.endswith(".count") and v is not None and v != "UNKNOWN"
    }
    present = sum(predicted.get(k) is not None and predicted.get(k) != "UNKNOWN" for k in available)
    correct, missing, invented, unsupported = 0, [], [], []
    decimal_names = {
        "quantity",
        "unit_price",
        "tax_rate",
        "net_amount",
        "tax_amount",
        "gross_amount",
        "subtotal_net",
        "tax_total",
        "total_gross",
    }
    for key, value in truth.items():
        output = predicted.get(key)
        equal = output == value
        if key.rsplit(".", 1)[-1] in decimal_names and value is not None and output is not None:
            try:
                equal = Decimal(value) == Decimal(output)
            except (InvalidOperation, TypeError):
                equal = False
        correct += bool(equal)
        if value is not None and output is None:
            missing.append(key)
        if value is None and output is not None:
            invented.append(key)
        if not equal and output is not None:
            unsupported.append(key)
    return {
        "correct": correct,
        "total": len(truth),
        "accuracy": str(Decimal(correct) / len(truth)) if truth else None,
        "expected_present": len(available),
        "extracted_present": present,
        "completeness": str(Decimal(present) / len(available)) if available else None,
        "missing_fields": missing,
        "invented_fields": invented,
        "incorrect_fields": unsupported,
    }


def grounding_metrics(expected, provenance):
    """Requires independently labelled support truth, never model confidence."""
    actual = {p["field"]: bool(p.get("grounded")) for p in provenance}
    tp = sum(supported and actual.get(path, False) for path, supported in expected.items())
    fp = sum(not supported and actual.get(path, False) for path, supported in expected.items())
    fn = sum(supported and not actual.get(path, False) for path, supported in expected.items())
    return {
        "labelled_fields": len(expected),
        "true_supported": tp,
        "false_supported": fp,
        "missed_supported": fn,
        "precision": str(Decimal(tp) / (tp + fp)) if tp + fp else None,
        "recall": str(Decimal(tp) / (tp + fn)) if tp + fn else None,
    }
