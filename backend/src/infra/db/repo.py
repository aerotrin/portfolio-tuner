from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from src.application.ports.account_data_repo import AccountDataRepository
from src.application.ports.market_data_repo import MarketDataRepository
from src.domain.entities.account import Transaction
from src.domain.entities.security import Bar, GlobalRates, Profile, Quote
from src.infra.db.models import BarDB, GlobalRatesDB, ProfileDB, QuoteDB
from src.infra.db.models import TransactionDB


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
            self.delete_global_rates()
            self.session.add(GlobalRatesDB(**global_rates.model_dump()))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def delete_global_rates(self) -> None:
        try:
            self.session.query(GlobalRatesDB).delete()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def upsert_quote(self, quote: Quote) -> None:
        try:
            self.delete_quote(quote.symbol)
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

    def delete_quote(self, symbol: str) -> None:
        try:
            self.session.query(QuoteDB).filter(QuoteDB.symbol == symbol).delete()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

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

    def upsert_bars(self, bars: List[Bar]) -> None:
        try:
            self.delete_bars(bars[0].symbol)
            self.session.add_all([BarDB(**bar.model_dump()) for bar in bars])
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def delete_bars(self, symbol: str) -> None:
        try:
            self.session.query(BarDB).filter(BarDB.symbol == symbol).delete()
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
            self.delete_profile(profile.symbol)
            self.session.add(ProfileDB(**profile.model_dump()))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def delete_profile(self, symbol: str) -> None:
        try:
            self.session.query(ProfileDB).filter(ProfileDB.symbol == symbol).delete()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise


class SqliteAccountDataRepository(AccountDataRepository):
    def __init__(self, session: Session):
        self.session = session

    def create_transaction(self, account_number: str, transaction: Transaction):
        try:
            self.session.add(
                TransactionDB(
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
            self.delete_transactions(account_number)
            self.session.add_all(
                [
                    TransactionDB(
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
