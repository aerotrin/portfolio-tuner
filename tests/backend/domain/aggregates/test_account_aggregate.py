from datetime import date

from src.backend.domain.aggregates.account import Account
from src.backend.domain.entities.account import Transaction


def _buy(symbol: str, qty: int, cost: float) -> Transaction:
    return Transaction(
        transaction_date=date(2025, 1, 2),
        settlement_date=date(2025, 1, 4),
        symbol=symbol,
        market="US",
        description="Common shares",
        quantity=qty,
        amount=-cost,
    )


def test_open_lots_are_stamped_with_account_number():
    account = Account("ACC-1", [_buy("AAPL", 10, 1000.0), _buy("MSFT", 5, 500.0)])

    assert len(account.open_positions) == 2
    assert all(lot.account == "ACC-1" for lot in account.open_positions)
