"""https://eodhd.com/financial-apis/category/historical-prices-live-data-apis"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
from typing import Any

import requests

from src.application.ports.market_data_provider import MarketDataProvider
from src.domain.entities.security import Bar, GlobalRates, Profile, Quote


@dataclass
class EODHDConfig:
    api_key: str
    base_url: str = "https://eodhd.com/api"
    timeout_sec: float = 10.0
    default_days_back: int = 365


class EODHDClient(MarketDataProvider):
    def __init__(self, config: EODHDConfig):
        self.cfg = config

        self.exchange_dir = self._fetch_exchange_directory()
        self.stock_dir_tsx = self._fetch_stock_directory_tsx()

    def _fetch_exchange_directory(self) -> dict[str, Any]:
        url = f"{self.cfg.base_url}/exchanges-list"
        try:
            response = requests.get(
                url,
                params={"api_token": self.cfg.api_key, "fmt": "json"},
                timeout=self.cfg.timeout_sec,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error retrieving exchange directory: {e}")
            raise e
        try:
            data = response.json()
        except ValueError as e:
            logging.error(f"Invalid JSON for exchange directory: {e}")
            raise e
        if not isinstance(data, list) or not data:
            logging.error("No exchange directory data retrieved")
            raise
        return {item["Code"]: item for item in data}

    def _fetch_stock_directory_tsx(self) -> dict[str, Any]:
        url = f"{self.cfg.base_url}/exchange-symbol-list/TO"
        try:
            response = requests.get(
                url,
                params={"api_token": self.cfg.api_key, "fmt": "json"},
                timeout=self.cfg.timeout_sec,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error retrieving stock directory: {e}")
            raise e
        try:
            data = response.json()
        except ValueError as e:
            logging.error(f"Invalid JSON for stock directory: {e}")
            raise e
        if not isinstance(data, list) or not data:
            logging.error("No stock directory data retrieved")
            raise
        return {item["Code"]: item for item in data}

    def fetch_quote(self, symbol: str) -> Quote:
        url = f"{self.cfg.base_url}/real-time/{symbol}"
        try:
            response = requests.get(
                url,
                params={"api_token": self.cfg.api_key, "fmt": "json"},
                timeout=self.cfg.timeout_sec,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error retrieving quote: {e}")
            raise e
        try:
            data = response.json()
        except ValueError as e:
            logging.error(f"Invalid JSON for quote: {e}")
            raise e
        if not data:
            logging.error("No quote data retrieved")
            raise
        s = symbol.split(".")[0]
        e = symbol.split(".")[-1]
        return Quote(
            symbol=symbol,
            name=self.stock_dir_tsx[s]["Name"],
            exchange=self.exchange_dir[e]["OperatingMIC"],
            open=data.get("open", 0.0),
            high=data.get("high", 0.0),
            low=data.get("low", 0.0),
            close=data.get("close", 0.0),
            currency=self.stock_dir_tsx[s]["Currency"],
            volume=data.get("volume", 0.0),
            change=data.get("change", 0.0),
            changePercent=data.get("change_p", 0.0) / 100.0,
            previousClose=data.get("previousClose", 0.0),
            timestamp=data.get("timestamp", datetime.now()),
        )

    def fetch_bars(
        self,
        symbol: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[Bar]:
        url = f"{self.cfg.base_url}/eod/{symbol}"
        try:
            response = requests.get(
                url,
                params={
                    "api_token": self.cfg.api_key,
                    "fmt": "json",
                    "from": from_date.strftime("%Y-%m-%d")
                    if from_date is not None
                    else (
                        date.today() - timedelta(days=self.cfg.default_days_back)
                    ).strftime("%Y-%m-%d"),
                    "to": to_date.strftime("%Y-%m-%d")
                    if to_date is not None
                    else date.today().strftime("%Y-%m-%d"),
                },
                timeout=self.cfg.timeout_sec,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error retrieving bars: {e}")
            raise e
        try:
            data = response.json()
        except ValueError as e:
            logging.error(f"Invalid JSON for bars: {e}")
            raise e
        if not isinstance(data, list) or not data:
            logging.error("No bars data retrieved")
            raise
        return [
            Bar(
                symbol=symbol,
                date=bar.get("date", ""),
                open=bar.get("open", ""),
                high=bar.get("high", ""),
                low=bar.get("low", ""),
                close=bar.get("close", ""),
                volume=bar.get("volume", ""),
            )
            for bar in data
        ]

    def fetch_global_rates(self) -> GlobalRates:
        return GlobalRates()  # Not implemented for EODHD

    def fetch_stock_profile(self, symbol: str) -> Profile:
        return Profile()  # Not paying for fundamental data

    def fetch_index_profile(self, symbol: str) -> Profile:
        return Profile()  # Not implemented for EODHD

    def fetch_commodity_profile(self, symbol: str) -> Profile:
        return Profile()  # Not implemented for EODHD

    def fetch_crypto_profile(self, symbol: str) -> Profile:
        return Profile()  # Not implemented for EODHD

    def fetch_forex_profile(self, symbol: str) -> Profile:
        return Profile()  # Not implemented for EODHD
