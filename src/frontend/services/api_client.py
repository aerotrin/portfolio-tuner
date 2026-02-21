import requests
from frontend.shared.env_loader import config
from frontend.shared.dto import (
    AccountCreateRequest,
    AccountPatchRequest,
    TransactionCreate,
)


class APIClient:
    def __init__(self, jwt_token: str | None = None):
        self.base_url = config.api_url
        self.session = requests.Session()
        self.timeout = (config.connect_timeout, config.read_timeout)
        if jwt_token:
            self.session.headers["Authorization"] = f"Bearer {jwt_token}"

    def update_token(self, jwt_token: str) -> None:
        self.session.headers["Authorization"] = f"Bearer {jwt_token}"

    def _get(self, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        resp = self.session.post(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        resp = self.session.patch(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        resp = self.session.delete(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def import_account(self, account_id: str, file_data) -> None:
        """Import transactions from an uploaded xlsx file. POST multipart to /admin/import-account. Pass account_id (UUID). Returns 202 with no body."""
        url = f"{self.base_url}/admin/import-account"
        filename = getattr(file_data, "name", "upload.xlsx") or "upload.xlsx"
        file_bytes = file_data.read()
        files = {
            "file": (
                filename,
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        data = {"account_id": account_id}
        resp = self.session.post(url, files=files, data=data, timeout=self.timeout)
        resp.raise_for_status()
        return None

    def refresh_rates(self):
        return self._post("/admin/refresh-rates")

    def refresh_security(self, symbol: str):
        return self._post(
            "/admin/refresh-security",
            params={"symbol": symbol},
        )

    def refresh_securities(self, symbols: list[str], intraday: bool = False):
        return self._post(
            "/admin/refresh-securities",
            params={"intraday": intraday},
            json=symbols,
        )

    def get_refresh_job(self, job_id: str):
        return self._get(f"/jobs/{job_id}")

    def get_rates(self):
        return self._get("/rates")

    def get_accounts(self):
        return self._get("/accounts")

    def get_account_details(self, account_id: str):
        return self._get(f"/accounts/{account_id}")

    def create_account(self, account: AccountCreateRequest):
        return self._post("/accounts", json=account.model_dump(mode="json"))

    def patch_account(self, account_id: str, account: AccountPatchRequest):
        return self._patch(
            f"/accounts/{account_id}", json=account.model_dump(mode="json")
        )

    def delete_account(self, account_id: str):
        return self._delete(f"/accounts/{account_id}")

    def get_account_summary(self, account_id: str):
        return self._get(f"/accounts/{account_id}/summary")

    def create_transaction(self, account_id: str, transaction: TransactionCreate):
        return self._post(
            f"/accounts/{account_id}/transactions",
            json=transaction.model_dump(mode="json"),
        )

    def get_account_transactions(self, account_id: str):
        return self._get(f"/accounts/{account_id}/transactions")

    def get_account_open_positions(self, account_id: str):
        return self._get(f"/accounts/{account_id}/open")

    def get_account_closed_lots(self, account_id: str):
        return self._get(f"/accounts/{account_id}/closed")

    def get_account_cash_flows(self, account_id: str):
        return self._get(f"/accounts/{account_id}/cash")

    def delete_transaction(self, account_id: str, transaction_id: str):
        return self._delete(f"/accounts/{account_id}/transactions/{transaction_id}")

    def get_available_symbols(self):
        return self._get("/securities")

    def get_portfolio_summary(self, account_id: str):
        return self._get(f"/accounts/{account_id}/portfolio")

    def get_portfolio_holdings(self, account_id: str):
        return self._get(f"/accounts/{account_id}/portfolio/holdings")

    def get_portfolio_indicators(self, account_id: str):
        return self._get(f"/accounts/{account_id}/portfolio/indicators")

    def get_portfolio_metrics(self, account_id: str):
        return self._get(f"/accounts/{account_id}/portfolio/metrics")

    def get_portfolio_correlation_matrix(self, account_id: str):
        return self._get(f"/accounts/{account_id}/portfolio/correlation")

    # TODO Implement portfolio simulation POST endpoint

    def get_security_batch_quotes(self, symbols: list[str]):
        return self._post("/securities/batch-quotes", json={"symbols": symbols})

    def get_security_batch_profiles(self, symbols: list[str]):
        return self._post("/securities/batch-profiles", json={"symbols": symbols})

    def get_security_batch_metrics(self, symbols: list[str]):
        return self._post("/securities/batch-metrics", json={"symbols": symbols})

    def get_security_batch_indicators(self, symbols: list[str]):
        return self._post("/securities/batch-indicators", json={"symbols": symbols})

    def get_security_quote(self, symbol: str):
        return self._get(f"/securities/{symbol}")

    def get_security_profile(self, symbol: str):
        return self._get(f"/securities/{symbol}/profile")

    def get_security_metrics(self, symbol: str):
        return self._get(f"/securities/{symbol}/metrics")

    def get_security_indicators(self, symbol: str):
        return self._get(f"/securities/{symbol}/indicators")

    def get_security_bars(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None
    ):
        params = {}
        if start_date is not None and end_date is not None:
            params = {"start_date": start_date, "end_date": end_date}
        return self._get(f"/securities/{symbol}/bars", params=params)

    def get_security_batch_bars(
        self,
        symbols: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
    ):
        payload = {"symbols": symbols, "start_date": start_date, "end_date": end_date}
        return self._post("/securities/batch-bars", json=payload)
