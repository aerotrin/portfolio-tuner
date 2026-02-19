from datetime import date, datetime
from types import SimpleNamespace

from src.backend.application.use_cases.portfolio import PortfolioManager
from src.backend.domain.entities.account import OpenLot
from src.backend.domain.entities.security import (
    GlobalRates,
    PerformanceMetric,
    TimeseriesIndicator,
)


class FakeMarketDataManager:
    def __init__(self):
        self.build_securities_batch_calls: list[list[str]] = []

    def build_securities_batch(self, symbols, start_date=None, end_date=None, rates=None):
        self.build_securities_batch_calls.append(list(symbols))
        return {symbol: SimpleNamespace(symbol=symbol) for symbol in symbols}

    def get_global_rates(self):
        return GlobalRates(rf_rate=4.5, fx_rate=1.34)


class FakeAccountManager:
    def __init__(self, positions: list[OpenLot], cash_balance: float = 0.0):
        self.positions = positions
        self.cash_balance = cash_balance
        self.calls: list[tuple[str, str | None]] = []

    def build_account(self, account_number: str, account_name: str | None = None):
        self.calls.append((account_number, account_name))
        return SimpleNamespace(
            open_positions=self.positions, cash_balance=self.cash_balance
        )


def test_build_portfolio_from_account_wires_positions_and_market_data(monkeypatch):
    positions = [
        OpenLot(
            symbol="AAPL",
            category="Equity",
            open_date=date(2024, 1, 1),
            open_qty=5,
            acb_per_sh=100.0,
            book_value=500.0,
        ),
        OpenLot(
            symbol="MSFT",
            category="Equity",
            open_date=date(2024, 1, 1),
            open_qty=2,
            acb_per_sh=200.0,
            book_value=400.0,
        ),
    ]
    fake_market = FakeMarketDataManager()
    fake_account = FakeAccountManager(positions=positions, cash_balance=250.0)

    captured = {}

    class CapturingPortfolio:
        def __init__(self, id, cash, positions, securities, rates):
            captured["id"] = id
            captured["cash"] = cash
            captured["positions"] = positions
            captured["securities"] = securities
            captured["rates"] = rates

    monkeypatch.setattr(
        "src.backend.application.use_cases.portfolio.Portfolio", CapturingPortfolio
    )

    manager = PortfolioManager(market_man=fake_market, account_man=fake_account)
    manager.build_portfolio_from_account("ACC-1", account_name="Main")

    assert fake_account.calls == [("ACC-1", "Main")]
    assert fake_market.build_securities_batch_calls == [["AAPL", "MSFT"]]
    assert captured["id"] == "ACC-1"
    assert captured["cash"] == 250.0
    assert captured["positions"] == positions
    assert set(captured["securities"].keys()) == {"AAPL", "MSFT"}


def test_portfolio_read_methods_pass_through(monkeypatch):
    indicator = TimeseriesIndicator(
        symbol="PORTF",
        date=datetime(2024, 1, 1),
        close=101.0,
        close_norm=1.01,
        daily_return=0.01,
        ema12=100.0,
        ema26=99.0,
        ema100=95.0,
        macd_12_26=1.0,
        macd_signal_9=0.8,
        macd_histogram=0.2,
        rsi=60.0,
        rsi_signal_5=58.0,
    )
    metric = PerformanceMetric(
        symbol="PORTF",
        name="Portfolio",
        exchange="N/A",
        currency="CAD",
        sharpe=1.3,
        volatility=0.2,
        sortino=1.1,
        max_drawdown=0.05,
        rsi_slope=0.1,
    )
    stub_portfolio = SimpleNamespace(
        id="ACC-1",
        book_value=1000.0,
        market_value=1100.0,
        total_value=1200.0,
        cash_balance=100.0,
        cash_pct=8.3,
        unrealized_gain=100.0,
        return_on_cost=0.1,
        return_on_value=0.083,
        pnl_intraday=5.0,
        holdings={"AAPL": SimpleNamespace(symbol="AAPL")},
        indicators=[indicator],
        metrics=metric,
        correlation_matrix={"labels": ["AAPL"], "values": [[1.0]]},
    )

    manager = PortfolioManager(
        market_man=FakeMarketDataManager(), account_man=FakeAccountManager([])
    )
    monkeypatch.setattr(
        manager,
        "build_portfolio_from_account",
        lambda *_args, **_kwargs: stub_portfolio,
    )

    summary = manager.get_portfolio_summary("ACC-1")
    assert summary.id == "ACC-1"
    assert summary.open_positions == ["AAPL"]
    assert manager.get_portfolio_holdings("ACC-1") is stub_portfolio.holdings
    assert manager.get_portfolio_indicators("ACC-1") == [indicator]
    assert manager.get_portfolio_metrics("ACC-1") == metric
    assert manager.get_portfolio_correlation_matrix("ACC-1") == {
        "labels": ["AAPL"],
        "values": [[1.0]],
    }


def test_run_simulated_portfolio_delegates_to_simulator(monkeypatch):
    fake_market = FakeMarketDataManager()
    manager = PortfolioManager(
        market_man=fake_market, account_man=FakeAccountManager([])
    )

    captured = {}

    class FakePortfolioSimulator:
        def __init__(self, securities, rates, n_p):
            captured["securities"] = securities
            captured["rates"] = rates
            captured["n_p"] = n_p
            self.ran = False

        def run_simulator(self):
            self.ran = True
            captured["ran"] = True

        def find_optimal_portfolio(self):
            assert self.ran is True
            return {
                "id": "PORTF_42",
                "metrics": {"sharpe": 1.8},
                "weights": {"AAPL": 0.6, "MSFT": 0.4},
            }

    monkeypatch.setattr(
        "src.backend.application.use_cases.portfolio.PortfolioSimulator",
        FakePortfolioSimulator,
    )

    result = manager.run_simulated_portfolio(symbols=["AAPL", "MSFT"], n_p=123)

    assert fake_market.build_securities_batch_calls == [["AAPL", "MSFT"]]
    assert captured["n_p"] == 123
    assert captured["ran"] is True
    assert result["id"] == "PORTF_42"
    assert set(result.keys()) == {"id", "metrics", "weights"}
