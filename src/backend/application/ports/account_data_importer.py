from typing import List, Protocol
from backend.domain.entities.account import Transaction


class AccountDataImporter(Protocol):
    def import_account(
        self, account_number: str, file_content: bytes
    ) -> List[Transaction]: ...
