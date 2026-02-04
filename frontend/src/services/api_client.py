import requests
from src.shared.env_loader import config
from src.shared.dto import TransactionCreate


class APIClient:
    def __init__(self):
        self.base_url = config.api_url
        self.session = requests.Session()
        self.timeout = (config.connect_timeout, config.read_timeout)

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

    def _delete(self, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        resp = self.session.delete(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def import_account(self, account_number: str, file_data) -> None:
        """Import transactions from an uploaded xlsx file. POST multipart to /admin/import-account. Returns 202 with no body."""
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
        data = {"account_number": account_number}
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

    def refresh_securities(self, symbols: list[str], intraday: bool = False) -> dict:
        return self._post(
            "/admin/refresh-securities",
            params={"intraday": intraday},
            json=symbols,
        )

    def get_refresh_job(self, job_id: str) -> dict:
        return self._get(f"/admin/refresh-securities/{job_id}")

    def get_rates(self):
        return self._get("/admin/rates")

    def get_account_summary(
        self, account: str, account_name: str | None = None
    ) -> dict:
        return self._get(
            f"/accounts/{account}",
            params={"account_name": account_name} if account_name is not None else {},
        )

    def create_transaction(self, account: str, transaction: TransactionCreate) -> dict:
        return self._post(
            f"/accounts/{account}/transactions",
            json=transaction.model_dump(mode="json"),
        )

    def get_account_transactions(
        self, account: str, account_name: str | None = None
    ) -> dict:
        return self._get(
            f"/accounts/{account}/transactions",
            params={"account_name": account_name} if account_name is not None else {},
        )

    def get_account_closed_lots(
        self, account: str, account_name: str | None = None
    ) -> dict:
        return self._get(
            f"/accounts/{account}/closed",
            params={"account_name": account_name} if account_name is not None else {},
        )

    def get_account_cash_flows(
        self, account: str, account_name: str | None = None
    ) -> dict:
        return self._get(
            f"/accounts/{account}/cash",
            params={"account_name": account_name} if account_name is not None else {},
        )

    def delete_transaction(self, account: str, transaction_id: str):
        return self._delete(f"/accounts/{account}/transactions/{transaction_id}")

    def get_available_symbols(self) -> dict:
        return self._get("/securities")

    def get_portfolio_summary(
        self, account: str, account_name: str | None = None
    ) -> dict:
        return self._get(
            f"/accounts/{account}/portfolio",
            params={"account_name": account_name} if account_name is not None else {},
        )

    def get_portfolio_holdings(
        self, account: str, account_name: str | None = None
    ) -> dict:
        return self._get(
            f"/accounts/{account}/portfolio/holdings",
            params={"account_name": account_name} if account_name is not None else {},
        )

    def get_portfolio_indicators(
        self, account: str, account_name: str | None = None
    ) -> dict:
        return self._get(
            f"/accounts/{account}/portfolio/indicators",
            params={"account_name": account_name} if account_name is not None else {},
        )

    def get_portfolio_metrics(
        self, account: str, account_name: str | None = None
    ) -> dict:
        return self._get(
            f"/accounts/{account}/portfolio/metrics",
            params={"account_name": account_name} if account_name is not None else {},
        )

    def get_portfolio_correlation_matrix(
        self, account: str, account_name: str | None = None
    ) -> dict:
        return self._get(
            f"/accounts/{account}/portfolio/correlation",
            params={"account_name": account_name} if account_name is not None else {},
        )

    # TODO Implement portfolio simulation POST endpoint

    def get_security_batch_quotes(self, symbols: list[str]) -> dict:
        return self._post("/securities/batch-quotes", json={"symbols": symbols})

    def get_security_batch_profiles(self, symbols: list[str]) -> dict:
        return self._post("/securities/batch-profiles", json={"symbols": symbols})

    def get_security_batch_metrics(self, symbols: list[str]) -> dict:
        return self._post("/securities/batch-metrics", json={"symbols": symbols})

    def get_security_batch_indicators(self, symbols: list[str]) -> dict:
        return self._post("/securities/batch-indicators", json={"symbols": symbols})

    def get_security_quote(self, symbol: str) -> dict:
        return self._get(f"/securities/{symbol}")

    def get_security_profile(self, symbol: str) -> dict:
        return self._get(f"/securities/{symbol}/profile")

    def get_security_metrics(self, symbol: str) -> dict:
        return self._get(f"/securities/{symbol}/metrics")

    def get_security_indicators(self, symbol: str) -> dict:
        return self._get(f"/securities/{symbol}/indicators")

    def get_security_bars(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None
    ) -> dict:
        params = {}
        if start_date is not None and end_date is not None:
            params = {"start_date": start_date, "end_date": end_date}
        return self._get(f"/securities/{symbol}/bars", params=params)

    def get_security_batch_bars(
        self,
        symbols: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        payload = {"symbols": symbols, "start_date": start_date, "end_date": end_date}
        return self._post("/securities/batch-bars", json=payload)
