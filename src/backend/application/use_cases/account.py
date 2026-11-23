from datetime import date, datetime, timezone
import uuid

from backend.application.ports.account_data_importer import AccountDataImporter
from backend.application.ports.account_data_repo import AccountDataRepository
from backend.domain.aggregates.account import Account
from backend.domain.analytics.fixed_income import (
    accrued_interest,
    days_to_maturity,
    instrument_status,
    interest_earned,
    ledger_description,
    maturity_value,
    new_instrument_symbol,
)
from backend.domain.entities.account import (
    AccountCreateRequest,
    AccountEntity,
    AccountPatchRequest,
    AccountRecordsDTO,
    Category,
    Currency,
    FixedIncomeCreateRequest,
    FixedIncomeInterestRequest,
    FixedIncomePreview,
    FixedIncomePreviewRequest,
    FixedIncomeRedemptionRequest,
    OpenLot,
    Transaction,
    TransactionCreateDTO,
    TransactionKind,
)


def _ledger_rate(
    instrument_currency: str, account_currency: str, usd_cad: float
) -> float:
    """Account-currency value of one unit of the instrument's currency."""
    if instrument_currency == account_currency:
        return 1.0
    return usd_cad if instrument_currency == Currency.USD else 1.0 / usd_cad


class AccountManager:
    """
    Application service for account-related use cases.

    - Sync transactions from an external source into the DB
    - Build Account aggregates from DB transactions
    - Provide view models (summaries, lists) for the API layer
    """

    def __init__(self, importer: AccountDataImporter, db: AccountDataRepository):
        self.importer = importer
        self.db = db

    def create_account(self, req: AccountCreateRequest, owner: str) -> AccountEntity:
        if self.db.account_exists_by_number(req.number):
            raise ValueError(f"Account with number {req.number!r} already exists")
        now = datetime.now(timezone.utc)
        account = AccountEntity(
            id=str(uuid.uuid4()),
            number=req.number,
            name=req.name,
            owner=owner,
            type=req.type,
            currency=req.currency,
            tax_status=req.tax_status,
            benchmark=req.benchmark,
            last_modified=now,
        )
        return self.db.add_account(account)

    def list_accounts(self) -> list[AccountEntity]:
        return self.db.list_accounts()

    def read_account(self, account_id: str) -> AccountEntity | None:
        return self.db.get_account(account_id)

    def patch_account(self, account_id: str, req: AccountPatchRequest) -> AccountEntity:
        account = self.db.get_account(account_id)
        if account is None:
            raise KeyError(f"Account {account_id} not found")
        if req.number is not None and req.number != account.number:
            if self.db.account_exists_by_number(req.number):
                raise ValueError(f"Account with number {req.number!r} already exists")
        now = datetime.now(timezone.utc)
        updated = AccountEntity(
            id=account.id,
            number=req.number if req.number is not None else account.number,
            name=req.name if req.name is not None else account.name,
            owner=account.owner,
            type=req.type if req.type is not None else account.type,
            currency=req.currency if req.currency is not None else account.currency,
            tax_status=(
                req.tax_status if req.tax_status is not None else account.tax_status
            ),
            benchmark=(
                req.benchmark if req.benchmark is not None else account.benchmark
            ),
            last_modified=now,
        )
        return self.db.update_account(updated)

    def delete_account(self, account_id: str) -> None:
        account = self.db.get_account(account_id)
        if account is None:
            raise KeyError(f"Account {account_id} not found")
        self.db.delete_account(account_id)

    def import_account(self, account_number: str, file_content: bytes) -> None:
        """Import transactions from uploaded xlsx and upsert for the account."""
        txs = self.importer.import_account(account_number, file_content)
        self.db.upsert_transactions(account_number, txs)

    def build_account(
        self, account_number: str, account_name: str | None = None
    ) -> Account:
        """Build a single Account aggregate from DB transactions."""
        txs = self.db.read_transactions(account_number)
        return Account(account_number, txs, account_name)

    def read_account_transactions(
        self,
        account_number: str,
    ) -> list[Transaction]:
        txs = self.db.read_transactions(account_number)
        return [Transaction.model_validate(tx) for tx in txs]

    def get_account_records(
        self,
        account_number: str,
        account_name: str | None = None,
    ) -> AccountRecordsDTO:
        account = self.build_account(account_number, account_name)
        return AccountRecordsDTO(
            transactions=account.transactions,
            open_positions=account.open_positions,
            closed_lots=account.closed_positions,
            cash_flows=account.cash_flows,
        )

    def create_transaction(
        self, account_number: str, payload: TransactionCreateDTO
    ) -> Transaction:
        data = payload.model_dump()
        tx = Transaction.model_validate(data)
        self.db.create_transaction(account_number, tx)
        return tx

    def delete_transaction(self, account_number: str, transaction_id: str) -> None:
        self.db.delete_transaction(account_number, transaction_id)

    @staticmethod
    def preview_fixed_income(req: FixedIncomePreviewRequest) -> FixedIncomePreview:
        today = date.today()
        accrued = accrued_interest(req.principal, req.terms, today)
        return FixedIncomePreview(
            term_days=(req.terms.maturity_date - req.terms.issue_date).days,
            interest_at_maturity=interest_earned(
                req.principal, req.terms, req.terms.maturity_date
            ),
            maturity_value=maturity_value(req.principal, req.terms),
            accrued_interest=accrued,
            value_today=req.principal + accrued,
            status=instrument_status(req.terms, today),
            days_to_maturity=days_to_maturity(req.terms, today),
        )

    def add_fixed_income(
        self, account: AccountEntity, req: FixedIncomeCreateRequest
    ) -> list[Transaction]:
        """Record the purchase of a GIC or term deposit, with its terms.

        Quantity follows the broker convention (whole dollars of face at a
        price of 100); the value always comes from the amount.
        """
        rate = _ledger_rate(req.currency, account.currency, req.fx_rate)
        cost = req.principal * rate
        common = dict(
            transaction_date=req.terms.issue_date,
            settlement_date=req.terms.issue_date,
            currency=req.currency,
            exchange_rate=rate,
        )
        txs = [
            Transaction(
                transaction_type=TransactionKind.BUY,
                symbol=new_instrument_symbol(req.terms),
                description=ledger_description(req.terms),
                quantity=max(1, round(req.principal)),
                price=100.0,
                amount=-cost,
                instrument_terms=req.terms.model_dump(),
                **common,
            )
        ]
        if req.funded_by_deposit:
            txs.insert(
                0,
                Transaction(
                    transaction_type=TransactionKind.EFT,
                    description="EFT",
                    amount=cost,
                    **common,
                ),
            )
        self.db.create_transactions(account.number, txs)
        return txs

    def _open_fixed_income_lot(self, account_number: str, symbol: str) -> OpenLot:
        for lot in self.build_account(account_number).open_positions:
            if lot.symbol == symbol and lot.category == Category.FIXED_INCOME:
                return lot
        raise KeyError(f"No open fixed-income holding {symbol!r} in this account")

    def redeem_fixed_income(
        self, account: AccountEntity, req: FixedIncomeRedemptionRequest
    ) -> list[Transaction]:
        """Close an instrument: principal back to cash, plus any final interest.

        Both rows are stored together so a redemption is never half recorded.
        """
        lot = self._open_fixed_income_lot(account.number, req.symbol)
        held = lot.principal or lot.book_value
        if req.principal > held + 0.005:
            raise ValueError(
                f"Redeemed principal {req.principal:,.2f} exceeds the "
                f"{held:,.2f} held"
            )
        currency = lot.currency or Currency.CAD
        rate = _ledger_rate(currency, account.currency, req.fx_rate)
        full = req.principal >= held - 0.005
        common = dict(
            transaction_date=req.transaction_date,
            settlement_date=req.transaction_date,
            symbol=req.symbol,
            currency=currency,
            exchange_rate=rate,
        )
        txs = []
        if req.interest > 0:
            txs.append(
                Transaction(
                    transaction_type=TransactionKind.INTEREST,
                    description=ledger_description(lot.terms, "INTEREST"),
                    amount=req.interest * rate,
                    **common,
                )
            )
        txs.append(
            Transaction(
                transaction_type=TransactionKind.REDEEMED,
                description=ledger_description(lot.terms, "REDEEMED FOR CASH"),
                quantity=(
                    lot.open_qty
                    if full
                    else max(1, round(lot.open_qty * req.principal / held))
                ),
                amount=req.principal * rate,
                **common,
            )
        )
        self.db.create_transactions(account.number, txs)
        return txs

    def record_fixed_income_interest(
        self, account: AccountEntity, req: FixedIncomeInterestRequest
    ) -> Transaction:
        """Record an interest payment received on an open instrument."""
        lot = self._open_fixed_income_lot(account.number, req.symbol)
        currency = lot.currency or Currency.CAD
        rate = _ledger_rate(currency, account.currency, req.fx_rate)
        tx = Transaction(
            transaction_date=req.transaction_date,
            settlement_date=req.transaction_date,
            transaction_type=TransactionKind.INTEREST,
            symbol=req.symbol,
            description=ledger_description(lot.terms, "INTEREST"),
            currency=currency,
            exchange_rate=rate,
            amount=req.amount * rate,
        )
        self.db.create_transactions(account.number, [tx])
        return tx
