from datetime import datetime, timezone
import uuid

from backend.application.ports.account_data_importer import AccountDataImporter
from backend.application.ports.account_data_repo import AccountDataRepository
from backend.domain.aggregates.account import Account
from backend.domain.entities.account import (
    AccountCreateRequest,
    AccountEntity,
    AccountPatchRequest,
    AccountRecordsDTO,
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
