from src.application.ports.account_data_importer import AccountDataImporter
from src.application.ports.account_data_repo import AccountDataRepository
from src.domain.aggregates.account import Account
from src.domain.entities.account import (
    AccountSummaryDTO,
    CashFlow,
    ClosedLot,
    OpenLot,
    Transaction,
    TransactionCreateDTO,
)


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

    # --- Write / ETL use case ---

    def import_account(self, account_number: str, file_content: bytes) -> None:
        """Import transactions from uploaded xlsx and upsert for the account."""
        txs = self.importer.import_account(account_number, file_content)
        self.db.upsert_transactions(account_number, txs)

    # --- Aggregate building helpers ---
    def build_account(
        self, account_number: str, account_name: str | None = None
    ) -> Account:
        """Build a single Account aggregate from DB transactions."""
        txs = self.db.read_transactions(account_number)
        return Account(account_number, txs, account_name)

    # --- Read / view-model helpers for API ---
    def get_account_summary(
        self,
        account_number: str,
        account_name: str | None = None,
    ) -> AccountSummaryDTO:
        account = self.build_account(account_number, account_name)
        return AccountSummaryDTO(
            number=account.number,
            name=account.name,
            cash_balance=account.cash_balance,
            book_value_securities=account.book_value_securities,
            net_investment=account.net_investment,
            open_positions=[p.symbol for p in account.open_positions],
        )

    def get_account_transactions(
        self,
        account_number: str,
        account_name: str | None = None,
    ) -> list[Transaction]:
        return self.build_account(account_number, account_name).transactions

    def get_account_open_positions(
        self,
        account_number: str,
        account_name: str | None = None,
    ) -> list[OpenLot]:
        return self.build_account(account_number, account_name).open_positions

    def get_account_closed_positions(
        self,
        account_number: str,
        account_name: str | None = None,
    ) -> list[ClosedLot]:
        return self.build_account(account_number, account_name).closed_positions

    def get_account_cash_flows(
        self,
        account_number: str,
        account_name: str | None = None,
    ) -> list[CashFlow]:
        return self.build_account(account_number, account_name).cash_flows

    def create_transaction(
        self, account_number: str, payload: TransactionCreateDTO
    ) -> Transaction:
        data = payload.model_dump()
        tx = Transaction.model_validate(data)
        self.db.create_transaction(account_number, tx)
        return tx

    def delete_transaction(self, account_number: str, transaction_id: str) -> None:
        self.db.delete_transaction(account_number, transaction_id)
