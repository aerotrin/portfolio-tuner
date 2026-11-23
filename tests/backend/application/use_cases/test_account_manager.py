from datetime import date, datetime, timezone

import pytest

from src.backend.application.use_cases.account import AccountManager
from src.backend.domain.entities.account import (
    AccountCreateRequest,
    AccountEntity,
    AccountPatchRequest,
    Currency,
    FixedIncomeCreateRequest,
    FixedIncomeInterestRequest,
    FixedIncomePreviewRequest,
    FixedIncomeRedemptionRequest,
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
        self.batches: list[int] = []  # size of each create_transactions call

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

    def create_transactions(self, account_number: str, transactions: list[Transaction]):
        self.batches.append(len(transactions))
        self.transactions.setdefault(account_number, []).extend(transactions)

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
    assert sum(cf.amount for cf in account.external_cash_flows) == pytest.approx(1000.0)

    assert account.cash_balance == pytest.approx(760.0)
    assert account.book_value_securities == pytest.approx(300.0)
    assert sum(cf.amount for cf in account.external_cash_flows) == pytest.approx(1000.0)
    assert [p.symbol for p in account.open_positions] == ["AAPL"]

    records = manager.get_account_records("ACC-1")
    assert len(records.open_positions) == 1
    assert len(records.closed_lots) == 1
    assert len(records.cash_flows) == 1


def test_return_of_capital_is_cash_flow_but_not_external_flow(
    sample_transactions: list[Transaction],
):
    roc = Transaction(
        transaction_date=date(2024, 1, 15),
        settlement_date=date(2024, 1, 17),
        transaction_type=TransactionKind.RETURN_OF_CAPITAL,
        symbol="AAPL",
        market="USA",
        description="Return of capital distribution",
        quantity=0,
        amount=40.0,
    )
    repo = FakeAccountDataRepository()
    repo.transactions["ACC-1"] = sample_transactions + [roc]
    manager = AccountManager(importer=FakeAccountDataImporter(), db=repo)

    account = manager.build_account("ACC-1")

    # Included in cash balance, excluded from external flows (net investment / MWRR)
    assert account.cash_balance == pytest.approx(800.0)
    assert sum(cf.amount for cf in account.external_cash_flows) == pytest.approx(1000.0)
    assert [cf.amount for cf in account.roc_distributions] == [pytest.approx(40.0)]

    records = manager.get_account_records("ACC-1")
    assert len(records.cash_flows) == 2


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


def _fixed_income_manager(
    currency: Currency = Currency.CAD,
) -> tuple[AccountManager, FakeAccountDataRepository, AccountEntity]:
    repo = FakeAccountDataRepository()
    manager = AccountManager(importer=FakeAccountDataImporter(), db=repo)
    account = manager.create_account(
        AccountCreateRequest(
            number="RRSP-1",
            name="Owner",
            type="RRSP",
            currency=currency,
            tax_status="Registered",
            benchmark="XIU.TO",
        ),
        owner="user-1",
    )
    return manager, repo, account


def _example_gic(**overrides) -> FixedIncomeCreateRequest:
    """1-year non-redeemable GIC, 2.45% paid at maturity, issued Dec 9 2025."""
    payload = dict(
        terms=dict(
            name="Example Bank",
            issue_date=date(2025, 12, 9),
            maturity_date=date(2026, 12, 9),
            annual_rate=0.0245,
        ),
        principal=26_104.02,
    )
    payload.update(overrides)
    return FixedIncomeCreateRequest(**payload)


def test_preview_fixed_income_reports_maturity_figures():
    preview = AccountManager.preview_fixed_income(
        FixedIncomePreviewRequest(
            **_example_gic().model_dump(include={"terms", "principal"})
        )
    )

    assert preview.term_days == 365
    assert preview.interest_at_maturity == pytest.approx(639.55, abs=0.005)
    assert preview.maturity_value == pytest.approx(26_743.57, abs=0.005)
    assert preview.value_today == pytest.approx(26_104.02 + preview.accrued_interest)


def test_add_fixed_income_records_a_buy_carrying_its_terms():
    manager, repo, account = _fixed_income_manager()

    (buy,) = manager.add_fixed_income(account, _example_gic())

    assert repo.batches == [1]
    assert buy.transaction_type == TransactionKind.BUY
    assert buy.symbol.startswith("GIC-2.45-20261209-")
    assert buy.transaction_date == date(2025, 12, 9)
    assert buy.quantity == 26_104
    assert buy.amount == pytest.approx(-26_104.02)
    assert buy.instrument_terms.annual_rate == pytest.approx(0.0245)

    built = manager.build_account("RRSP-1")
    (lot,) = built.open_positions
    assert lot.symbol == buy.symbol
    assert lot.principal == pytest.approx(26_104.02)
    assert lot.terms.maturity_date == date(2026, 12, 9)
    assert built.cash_balance == pytest.approx(-26_104.02)


def test_add_fixed_income_funded_by_deposit_leaves_cash_unchanged():
    manager, repo, account = _fixed_income_manager()

    deposit, buy = manager.add_fixed_income(
        account, _example_gic(funded_by_deposit=True)
    )

    # Stored together: both rows or neither
    assert repo.batches == [2]
    assert deposit.transaction_type == TransactionKind.EFT
    assert deposit.amount == pytest.approx(26_104.02)

    built = manager.build_account("RRSP-1")
    assert built.cash_balance == pytest.approx(0.0)
    assert [f.amount for f in built.external_cash_flows] == [pytest.approx(26_104.02)]
    assert len(built.open_positions) == 1


def test_usd_instrument_in_a_cad_account_books_cad_and_keeps_native_principal():
    manager, _repo, account = _fixed_income_manager()

    (buy,) = manager.add_fixed_income(
        account, _example_gic(principal=10_000.0, currency="USD", fx_rate=1.4)
    )

    assert buy.amount == pytest.approx(-14_000.0)
    (lot,) = manager.build_account("RRSP-1").open_positions
    assert lot.currency == "USD"
    assert lot.principal == pytest.approx(10_000.0)
    assert lot.book_value == pytest.approx(14_000.0)


def test_redeem_fixed_income_closes_the_holding_and_pays_interest():
    manager, repo, account = _fixed_income_manager()
    (buy,) = manager.add_fixed_income(account, _example_gic(funded_by_deposit=True))[1:]

    interest, redeemed = manager.redeem_fixed_income(
        account,
        FixedIncomeRedemptionRequest(
            symbol=buy.symbol,
            transaction_date=date(2026, 12, 9),
            principal=26_104.02,
            interest=639.55,
        ),
    )

    assert repo.batches == [2, 2]
    assert interest.transaction_type == TransactionKind.INTEREST
    assert redeemed.transaction_type == TransactionKind.REDEEMED
    assert redeemed.quantity == 26_104

    built = manager.build_account("RRSP-1")
    assert built.open_positions == []
    (closed,) = built.closed_positions
    assert closed.gain == pytest.approx(0.0)
    assert built.cash_balance == pytest.approx(26_104.02 + 639.55)
    (income,) = built.income
    assert income.symbol == buy.symbol
    assert income.amount == pytest.approx(639.55)


def test_redeem_fixed_income_rejects_unknown_holding_and_over_redemption():
    manager, repo, account = _fixed_income_manager()
    (buy,) = manager.add_fixed_income(account, _example_gic())

    with pytest.raises(KeyError):
        manager.redeem_fixed_income(
            account,
            FixedIncomeRedemptionRequest(
                symbol="GIC-9.99-20300101",
                transaction_date=date(2026, 12, 9),
                principal=100.0,
            ),
        )
    with pytest.raises(ValueError):
        manager.redeem_fixed_income(
            account,
            FixedIncomeRedemptionRequest(
                symbol=buy.symbol,
                transaction_date=date(2026, 12, 9),
                principal=30_000.0,
            ),
        )
    assert repo.batches == [1]


def test_record_fixed_income_interest_is_attributed_to_the_holding():
    manager, _repo, account = _fixed_income_manager()
    (buy,) = manager.add_fixed_income(account, _example_gic())

    manager.record_fixed_income_interest(
        account,
        FixedIncomeInterestRequest(
            symbol=buy.symbol, transaction_date=date(2026, 6, 9), amount=320.0
        ),
    )

    (lot,) = manager.build_account("RRSP-1").open_positions
    assert lot.interest_received == pytest.approx(320.0)


def test_ledger_imported_gic_can_be_redeemed_by_its_derived_key():
    """A GIC that came from the ledger has no stored key; the redemption rows
    written for it must still resolve to the same holding."""
    manager, repo, account = _fixed_income_manager()
    repo.create_transaction(
        "RRSP-1",
        Transaction(
            transaction_date=date(2023, 11, 6),
            settlement_date=date(2023, 11, 7),
            transaction_type=TransactionKind.BUY,
            symbol="",
            description=(
                "CIBC FLEXIBLE GIC               AM NON-TRANSFERABLE Maturity "
                "NOV 07 2024 Coupon         5.00  FLEXIBLE GIC"
            ),
            quantity=20000,
            price=100.0,
            exchange_rate=1.0,
            amount=-20000.0,
        ),
    )

    manager.redeem_fixed_income(
        account,
        FixedIncomeRedemptionRequest(
            symbol="GIC-5.00-20241107",
            transaction_date=date(2024, 11, 7),
            principal=20_000.0,
            interest=1_000.0,
        ),
    )

    built = manager.build_account("RRSP-1")
    assert built.open_positions == []
    assert built.cash_balance == pytest.approx(1_000.0)
    assert built.income[0].symbol == "GIC-5.00-20241107"
