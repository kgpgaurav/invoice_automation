"""Shared INR line arithmetic, independent of spending caps and approvals."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.finance_contracts import money


@dataclass(frozen=True)
class LineAmounts:
    net: Decimal
    tax: Decimal
    gross: Decimal


@dataclass(frozen=True)
class OrderAmounts:
    subtotal_net: Decimal
    tax_total: Decimal
    total_gross: Decimal
    lines: tuple[LineAmounts, ...]


def order_amounts(lines) -> OrderAmounts:
    # Inputs have the existing finite 18-digit quantity/price constraints. Their
    # product needs more than Decimal's default 28 significant digits.
    with localcontext() as context:
        context.prec = 64
        amounts = []
        for line in lines:
            net = money(line.quantity * line.unit_price)
            tax = money(net * line.tax_rate / 100)
            amounts.append(LineAmounts(net, tax, net + tax))
        return OrderAmounts(
            sum((line.net for line in amounts), Decimal("0.00")),
            sum((line.tax for line in amounts), Decimal("0.00")),
            sum((line.gross for line in amounts), Decimal("0.00")),
            tuple(amounts),
        )


def supported_amounts(lines) -> OrderAmounts:
    amounts = order_amounts(lines)
    if amounts.total_gross >= Decimal("10000000000000000"):
        raise ValueError("Line totals exceed supported INR precision")
    return amounts
