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
        "accuracy": str(Decimal(correct) / len(truth)),
        "missing_fields": missing,
        "invented_fields": invented,
        "incorrect_fields": unsupported,
    }
