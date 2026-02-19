from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.application.ports.account_data_repo import AccountDataRepository
from backend.application.ports.market_data_repo import MarketDataRepository
from backend.domain.entities.account import AccountEntity, Transaction
from backend.domain.entities.security import Bar, GlobalRates, Profile, Quote
from backend.infra.db.models import AccountDB, BarDB, GlobalRatesDB, ProfileDB, QuoteDB
from backend.infra.db.models import TransactionDB


class SqliteMarketDataRepository(MarketDataRepository):
    def __init__(self, session: Session):
        self.session = session

    def read_securities_list(self) -> List[str]:
        rows = self.session.query(QuoteDB).all()
        if rows is None or len(rows) == 0:
            return []
        return [quote.symbol for quote in rows]

    def read_global_rates(self) -> GlobalRates | None:
        row = self.session.query(GlobalRatesDB).first()
        if row is None:
            return None
        return GlobalRates.model_validate(row)

    def upsert_global_rates(self, global_rates: GlobalRates) -> None:
        try:
            self.session.query(GlobalRatesDB).delete()
            self.session.add(GlobalRatesDB(**global_rates.model_dump()))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def upsert_quote(self, quote: Quote) -> None:
        try:
            self.session.query(QuoteDB).filter(QuoteDB.symbol == quote.symbol).delete()
            self.session.add(QuoteDB(**quote.model_dump()))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def read_quote(self, symbol: str) -> Quote | None:
        row = self.session.query(QuoteDB).filter(QuoteDB.symbol == symbol).first()
        if row is None:
            return None
        return Quote.model_validate(row)

    def read_quotes(self, symbols: list[str]) -> list[Quote]:
        rows = self.session.query(QuoteDB).filter(QuoteDB.symbol.in_(symbols)).all()
        if rows is None or len(rows) == 0:
            return []
        return [Quote.model_validate(row) for row in rows]

    def read_bars(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Bar]:
        filters = [BarDB.symbol == symbol]
        if start_date:
            filters.append(BarDB.date >= start_date)
        if end_date:
            filters.append(BarDB.date <= end_date)
        rows = self.session.query(BarDB).filter(*filters).all()
        if rows is None or len(rows) == 0:
            return []
        return [Bar.model_validate(bar) for bar in rows]

    def read_batch_bars(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict[str, List[Bar]]:
        filters = [BarDB.symbol.in_(symbols)]
        if start_date:
            filters.append(BarDB.date >= start_date)
        if end_date:
            filters.append(BarDB.date <= end_date)
        rows = self.session.query(BarDB).filter(*filters).all()
        result: dict[str, List[Bar]] = {symbol: [] for symbol in symbols}
        for row in rows:
            result[row.symbol].append(Bar.model_validate(row))
        return result

    def upsert_bars(self, bars: List[Bar]) -> None:
        try:
            self.session.query(BarDB).filter(BarDB.symbol == bars[0].symbol).delete()
            self.session.add_all([BarDB(**bar.model_dump()) for bar in bars])
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def read_profile(self, symbol: str) -> Profile | None:
        row = self.session.query(ProfileDB).filter(ProfileDB.symbol == symbol).first()
        if row is None:
            return None
        return Profile.model_validate(row)

    def read_profiles(self, symbols: list[str]) -> list[Profile]:
        rows = self.session.query(ProfileDB).filter(ProfileDB.symbol.in_(symbols)).all()
        if rows is None or len(rows) == 0:
            return []
        return [Profile.model_validate(row) for row in rows]

    def upsert_profile(self, profile: Profile) -> None:
        try:
            self.session.query(ProfileDB).filter(
                ProfileDB.symbol == profile.symbol
            ).delete()
            self.session.add(ProfileDB(**profile.model_dump()))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise


class SqliteAccountDataRepository(AccountDataRepository):
    def __init__(self, session: Session):
        self.session = session

    # --- Account CRUD ---

    def add_account(self, account: AccountEntity) -> AccountEntity:
        try:
            row = AccountDB(
                id=account.id,
                number=account.number,
                owner=account.owner,
                type=account.type,
                currency=account.currency,
                tax_status=account.tax_status,
                benchmark=account.benchmark,
                last_modified=account.last_modified,
            )
            self.session.add(row)
            self.session.commit()
            return account
        except Exception:
            self.session.rollback()
            raise

    def get_account(self, account_id: str) -> AccountEntity | None:
        row = self.session.query(AccountDB).filter(AccountDB.id == account_id).first()
        if row is None:
            return None
        return AccountEntity.model_validate(row)

    def get_account_by_number(self, number: str) -> AccountEntity | None:
        row = self.session.query(AccountDB).filter(AccountDB.number == number).first()
        if row is None:
            return None
        return AccountEntity.model_validate(row)

    def list_accounts(self) -> List[AccountEntity]:
        rows = self.session.query(AccountDB).all()
        if rows is None or len(rows) == 0:
            return []
        return [AccountEntity.model_validate(row) for row in rows]

    def update_account(self, account: AccountEntity) -> AccountEntity:
        try:
            row = (
                self.session.query(AccountDB).filter(AccountDB.id == account.id).first()
            )
            if row is None:
                raise KeyError(f"Account {account.id} not found")
            row.number = account.number
            row.owner = account.owner
            row.type = account.type
            row.currency = account.currency
            row.tax_status = account.tax_status
            row.benchmark = account.benchmark
            row.last_modified = account.last_modified
            self.session.commit()
            return account
        except Exception:
            self.session.rollback()
            raise

    def delete_account(self, account_id: str) -> None:
        try:
            self.session.query(AccountDB).filter(AccountDB.id == account_id).delete()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def account_exists_by_number(self, number: str) -> bool:
        return (
            self.session.query(AccountDB).filter(AccountDB.number == number).first()
            is not None
        )

    # --- Transaction operations (resolve account_id from account_number) ---

    def _resolve_account_id(self, account_number: str) -> str:
        acc = self.get_account_by_number(account_number)
        if acc is None:
            raise ValueError(f"Account with number {account_number!r} not found")
        return acc.id

    def create_transaction(self, account_number: str, transaction: Transaction):
        try:
            account_id = self._resolve_account_id(account_number)
            self.session.add(
                TransactionDB(
                    account_id=account_id,
                    account_number=account_number,
                    **transaction.model_dump(),
                )
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def upsert_transactions(self, account_number: str, transactions: List[Transaction]):
        try:
            account_id = self._resolve_account_id(account_number)
            self.delete_transactions(account_number)
            self.session.add_all(
                [
                    TransactionDB(
                        account_id=account_id,
                        account_number=account_number,
                        **transaction.model_dump(),
                    )
                    for transaction in transactions
                ]
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def read_transactions(self, account_number: str) -> List[Transaction]:
        rows = (
            self.session.query(TransactionDB)
            .filter(TransactionDB.account_number == account_number)
            .all()
        )
        if rows is None or len(rows) == 0:
            return []
        return [Transaction.model_validate(row) for row in rows]

    def delete_transactions(self, account_number: str):
        try:
            self.session.query(TransactionDB).filter(
                TransactionDB.account_number == account_number
            ).delete()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def delete_transaction(self, account_number: str, transaction_id: str):
        try:
            self.session.query(TransactionDB).filter(
                TransactionDB.account_number == account_number,
                TransactionDB.id == transaction_id,
            ).delete()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
