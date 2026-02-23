from datetime import date, datetime, timezone

import pytest

from src.backend.application.use_cases.account import AccountManager
from src.backend.domain.entities.account import (
    AccountCreateRequest,
    AccountEntity,
    AccountPatchRequest,
    Currency,
    Transaction,
    TransactionCreateDTO,
    TransactionKind,
)


class FakeAccountDataImporter:
    def __init__(self, transactions: list[Transaction] | None = None):
        self.transactions = transactions or []
        self.calls: list[tuple[str, bytes]] = []

    def import_account(
        self, account_number: str, file_content: bytes
    ) -> list[Transaction]:
        self.calls.append((account_number, file_content))
        return self.transactions


class FakeAccountDataRepository:
    def __init__(self):
        self.accounts: dict[str, AccountEntity] = {}
        self.transactions: dict[str, list[Transaction]] = {}

    def add_account(self, account: AccountEntity) -> AccountEntity:
        self.accounts[account.id] = account
        return account

    def get_account(self, account_id: str) -> AccountEntity | None:
        return self.accounts.get(account_id)

    def get_account_by_number(self, number: str) -> AccountEntity | None:
        for account in self.accounts.values():
            if account.number == number:
                return account
        return None

    def list_accounts(self) -> list[AccountEntity]:
        return list(self.accounts.values())

    def update_account(self, account: AccountEntity) -> AccountEntity:
        self.accounts[account.id] = account
        return account

    def delete_account(self, account_id: str) -> None:
        self.accounts.pop(account_id, None)

    def account_exists_by_number(self, number: str) -> bool:
        return any(a.number == number for a in self.accounts.values())

    def create_transaction(self, account_number: str, transaction: Transaction):
        self.transactions.setdefault(account_number, []).append(transaction)

    def read_transactions(self, account_number: str) -> list[Transaction]:
        return list(self.transactions.get(account_number, []))

    def upsert_transactions(self, account_number: str, transactions: list[Transaction]):
        self.transactions.setdefault(account_number, [])
        self.transactions[account_number].extend(transactions)

    def delete_transactions(self, account_number: str):
        self.transactions.pop(account_number, None)

    def delete_transaction(self, account_number: str, transaction_id: str):
        self.transactions[account_number] = [
            tx
            for tx in self.transactions.get(account_number, [])
            if tx.id != transaction_id
        ]


@pytest.fixture
def sample_transactions() -> list[Transaction]:
    return [
        Transaction(
            transaction_date=date(2024, 1, 2),
            settlement_date=date(2024, 1, 2),
            transaction_type=TransactionKind.CONTRIB,
            description="Initial contribution",
            amount=1000.0,
            quantity=0,
            symbol="",
            market="",
        ),
        Transaction(
            transaction_date=date(2024, 1, 3),
            settlement_date=date(2024, 1, 5),
            transaction_type=TransactionKind.BUY,
            symbol="AAPL",
            market="USA",
            description="Buy AAPL",
            quantity=10,
            price=50.0,
            amount=-500.0,
        ),
        Transaction(
            transaction_date=date(2024, 1, 10),
            settlement_date=date(2024, 1, 12),
            transaction_type=TransactionKind.SELL,
            symbol="AAPL",
            market="USA",
            description="Sell AAPL",
            quantity=4,
            price=65.0,
            amount=260.0,
        ),
    ]


def test_build_account_and_summary_and_view_accessors(
    sample_transactions: list[Transaction],
):
    repo = FakeAccountDataRepository()
    repo.transactions["ACC-1"] = sample_transactions
    manager = AccountManager(importer=FakeAccountDataImporter(), db=repo)

    account = manager.build_account("ACC-1", account_name="Primary")
    assert account.number == "ACC-1"
    assert account.name == "Primary"
    assert account.cash_balance == pytest.approx(760.0)
    assert account.book_value_securities == pytest.approx(300.0)
    assert account.net_investment == pytest.approx(1000.0)

    assert account.cash_balance == pytest.approx(760.0)
    assert account.book_value_securities == pytest.approx(300.0)
    assert account.net_investment == pytest.approx(1000.0)
    assert [p.symbol for p in account.open_positions] == ["AAPL"]

    records = manager.get_account_records("ACC-1")
    assert len(records.open_positions) == 1
    assert len(records.closed_lots) == 1
    assert len(records.cash_flows) == 1


def test_create_account_rejects_duplicate_account_number():
    repo = FakeAccountDataRepository()
    existing = AccountEntity(
        id="existing",
        number="001",
        name="Jane Doe",
        owner="Jane",
        type="TFSA",
        currency=Currency.CAD,
        tax_status="Registered",
        benchmark="SPY",
        last_modified=datetime.now(timezone.utc),
    )
    repo.add_account(existing)
    manager = AccountManager(importer=FakeAccountDataImporter(), db=repo)

    req = AccountCreateRequest(
        number="001",
        name="John Smith",
        type="RRSP",
        currency=Currency.CAD,
        tax_status="Registered",
        benchmark="QQQ",
    )

    with pytest.raises(ValueError, match="already exists"):
        manager.create_account(req, owner="user-123")


def test_patch_account_rejects_missing_account_id():
    manager = AccountManager(
        importer=FakeAccountDataImporter(), db=FakeAccountDataRepository()
    )

    with pytest.raises(KeyError, match="not found"):
        manager.patch_account("missing", AccountPatchRequest(name="Updated"))


def test_delete_account_rejects_missing_account_id():
    manager = AccountManager(
        importer=FakeAccountDataImporter(), db=FakeAccountDataRepository()
    )

    with pytest.raises(KeyError, match="not found"):
        manager.delete_account("missing")


def test_patch_account_rejects_duplicate_number():
    repo = FakeAccountDataRepository()
    first = AccountEntity(
        id="a1",
        number="001",
        name="Jane Doe",
        owner="Jane",
        type="TFSA",
        currency=Currency.CAD,
        tax_status="Registered",
        benchmark="SPY",
        last_modified=datetime.now(timezone.utc),
    )
    second = AccountEntity(
        id="a2",
        number="002",
        name="John Smith",
        owner="John",
        type="RRSP",
        currency=Currency.USD,
        tax_status="Non-Registered",
        benchmark="QQQ",
        last_modified=datetime.now(timezone.utc),
    )
    repo.add_account(first)
    repo.add_account(second)
    manager = AccountManager(importer=FakeAccountDataImporter(), db=repo)

    with pytest.raises(ValueError, match="already exists"):
        manager.patch_account("a2", AccountPatchRequest(number="001"))


def test_get_account_returns_none_for_missing_id():
    manager = AccountManager(
        importer=FakeAccountDataImporter(), db=FakeAccountDataRepository()
    )
    assert manager.read_account("missing") is None


def test_create_transaction_roundtrip_through_repository():
    repo = FakeAccountDataRepository()
    manager = AccountManager(importer=FakeAccountDataImporter(), db=repo)

    payload = TransactionCreateDTO(
        transaction_date=date(2024, 3, 1),
        transaction_type=TransactionKind.DIVIDEND,
        symbol="AAPL",
        market="USA",
        description="Dividend",
        quantity=0,
        currency=Currency.USD,
        price=0.0,
        commission=0.0,
        exchange_rate=1.0,
        fees_paid=0.0,
        amount=10.0,
    )

    tx = manager.create_transaction("ACC-1", payload)

    assert tx.symbol == "AAPL"
    assert len(repo.read_transactions("ACC-1")) == 1
