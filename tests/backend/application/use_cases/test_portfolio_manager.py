import asyncio
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from src.backend.application.use_cases.portfolio import PortfolioManager
from src.backend.domain.aggregates.security import Security
from src.backend.domain.entities.account import (
    AccountEntity,
    CashFlow,
    Category,
    Currency,
    OpenLot,
    TransactionKind,
)
from src.backend.domain.entities.security import (
    GlobalRates,
    PerformanceMetric,
    TimeseriesIndicator,
)
from tests.backend.conftest import (
    build_bars,
    build_global_rates,
    build_profile,
    build_quote,
)


class FakeMarketDataManager:
    def __init__(self):
        self.build_securities_batch_calls: list[dict] = []

    async def build_securities_batch_async(
        self, symbols, start_date=None, end_date=None, rates=None
    ):
        self.build_securities_batch_calls.append(
            {"symbols": list(symbols), "start_date": start_date, "end_date": end_date}
        )
        return {symbol: SimpleNamespace(symbol=symbol) for symbol in symbols}

    def read_global_rates(self):
        return GlobalRates(rf_rate=0.045, fx_rate=1.34)


class FakeAccountManager:
    def __init__(self, positions: list[OpenLot], cash_balance: float = 0.0):
        self.positions = positions
        self.cash_balance = cash_balance
        self.calls: list[tuple[str, str | None]] = []

    def build_account(self, account_number: str, account_name: str | None = None):
        self.calls.append((account_number, account_name))
        return SimpleNamespace(
            open_positions=self.positions,
            cash_balance=self.cash_balance,
            external_cash_flows=[],
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
        def __init__(self, id, cash, external_cash_flows, positions, securities, rates):
            captured["id"] = id
            captured["cash"] = cash
            captured["positions"] = positions
            captured["securities"] = securities
            captured["rates"] = rates

    monkeypatch.setattr(
        "src.backend.application.use_cases.portfolio.Portfolio", CapturingPortfolio
    )

    manager = PortfolioManager(market_man=fake_market, account_man=fake_account)
    asyncio.run(manager._build_portfolio_from_account("ACC-1", account_name="Main"))

    assert fake_account.calls == [("ACC-1", "Main")]
    assert fake_market.build_securities_batch_calls == [
        {"symbols": ["AAPL", "MSFT"], "start_date": None, "end_date": None}
    ]
    assert captured["id"] == "ACC-1"
    assert captured["cash"] == 250.0
    assert captured["positions"] == positions
    assert set(captured["securities"].keys()) == {"AAPL", "MSFT"}


def test_build_portfolio_from_account_forwards_date_filter(monkeypatch):
    """start_date and end_date are forwarded to build_securities_batch_async."""
    fake_market = FakeMarketDataManager()
    fake_account = FakeAccountManager(positions=[], cash_balance=0.0)

    class CapturingPortfolio:
        def __init__(self, id, cash, external_cash_flows, positions, securities, rates):
            pass

    monkeypatch.setattr(
        "src.backend.application.use_cases.portfolio.Portfolio", CapturingPortfolio
    )

    manager = PortfolioManager(market_man=fake_market, account_man=fake_account)
    start = date(2024, 1, 1)
    end = date(2024, 12, 31)
    asyncio.run(
        manager._build_portfolio_from_account("ACC-1", start_date=start, end_date=end)
    )

    assert fake_market.build_securities_batch_calls == [
        {"symbols": [], "start_date": start, "end_date": end}
    ]


def test_portfolio_read_methods_pass_through(monkeypatch):
    indicator = TimeseriesIndicator(
        symbol="PORTF",
        date=date(2024, 1, 1),
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
        net_investment=0.0,
        mwrr=0.0,
        pnl_intraday=5.0,
        holdings={},
        indicators=[indicator],
        metrics=metric,
        correlation_matrix=None,
        securities={},
    )

    manager = PortfolioManager(
        market_man=FakeMarketDataManager(), account_man=FakeAccountManager([])
    )

    async def fake_build(*_args, **_kwargs):
        return stub_portfolio

    monkeypatch.setattr(manager, "_build_portfolio_from_account", fake_build)

    snap = asyncio.run(manager.get_portfolio("ACC-1"))
    assert snap.summary.id == "ACC-1"
    assert snap.summary.open_positions == []
    assert snap.holdings == {}
    assert len(snap.indicators) == 1
    assert snap.indicators[0].model_dump() == indicator.model_dump()
    assert snap.metrics.model_dump() == metric.model_dump()
    assert snap.correlation_matrix is None


def test_get_portfolio_includes_per_security_analytics(monkeypatch):
    """get_portfolio returns per-security analytics and forwards date params."""
    rates = build_global_rates()
    aapl_sec = Security(
        quote=build_quote("AAPL"),
        bars=build_bars("AAPL", closes=[100.0, 101.0, 102.0, 103.0, 104.0]),
        profile=build_profile("AAPL"),
        rates=rates,
    )
    stub_portfolio = SimpleNamespace(
        id="ACC-1",
        book_value=500.0,
        market_value=550.0,
        total_value=650.0,
        cash_balance=100.0,
        cash_pct=0.15,
        unrealized_gain=50.0,
        return_on_cost=0.1,
        return_on_value=0.077,
        net_investment=0.0,
        mwrr=0.0,
        pnl_intraday=2.0,
        holdings={},
        indicators=[],
        metrics=PerformanceMetric(
            symbol="PORTF", name="Portfolio", exchange="N/A", currency="CAD"
        ),
        correlation_matrix=None,
        securities={"AAPL": aapl_sec},
    )

    build_calls: list[dict] = []

    async def fake_build(
        account_number, account_name=None, start_date=None, end_date=None
    ):
        build_calls.append({"start_date": start_date, "end_date": end_date})
        return stub_portfolio

    manager = PortfolioManager(
        market_man=FakeMarketDataManager(), account_man=FakeAccountManager([])
    )
    monkeypatch.setattr(manager, "_build_portfolio_from_account", fake_build)

    start = date(2024, 1, 1)
    end = date(2024, 12, 31)
    snap = asyncio.run(manager.get_portfolio("ACC-1", start_date=start, end_date=end))

    assert build_calls == [{"start_date": start, "end_date": end}]
    assert snap.summary.id == "ACC-1"
    assert snap.summary.open_positions == []
    assert set(snap.securities.keys()) == {"AAPL"}
    assert snap.securities["AAPL"].quote.symbol == "AAPL"


# ---------------------------------------------------------------------------
# get_total_portfolio
# ---------------------------------------------------------------------------

FX = 1.35


def _entity(
    id: str, number: str, currency: Currency = Currency.CAD, type: str = "TFSA"
) -> AccountEntity:
    return AccountEntity(
        id=id,
        number=number,
        name=f"Acct {number}",
        owner="user-1",
        type=type,
        currency=currency,
        tax_status="Registered",
        benchmark="XIU.TO",
        last_modified=datetime(2025, 1, 1),
    )


def _equity_lot(symbol: str, qty: int, book: float, account: str) -> OpenLot:
    """Lot as Account.build() produces it — stamped with its account number."""
    return OpenLot(
        symbol=symbol,
        account=account,
        category=Category.EQUITY,
        open_date=date(2025, 1, 2),
        open_qty=qty,
        acb_per_sh=book / qty,
        book_value=book,
    )


def _contribution(amount: float, on: date) -> CashFlow:
    return CashFlow(
        transaction_date=on,
        category=Category.CASH,
        transaction_type=TransactionKind.CONTRIB,
        description="contribution",
        market="CASH",
        currency=Currency.CAD,
        amount=amount,
    )


class FakeMultiAccountManager:
    def __init__(self, entities: list[AccountEntity], accounts_by_number: dict):
        self.entities = entities
        self.accounts_by_number = accounts_by_number

    def list_accounts(self):
        return self.entities

    def build_account(self, account_number: str, account_name: str | None = None):
        return self.accounts_by_number[account_number]


class RealSecurityMarketManager:
    """Returns real Security aggregates so the total Portfolio fully builds."""

    def __init__(self):
        self.calls: list[list[str]] = []

    async def build_securities_batch_async(
        self, symbols, start_date=None, end_date=None, rates=None
    ):
        self.calls.append(list(symbols))
        closes = [100.0 + i * 0.1 for i in range(60)]
        return {
            s: Security(
                quote=build_quote(symbol=s),  # USD, close=110
                bars=build_bars(s, closes=closes),
                profile=build_profile(s),
                rates=build_global_rates(fx_rate=FX),
            )
            for s in set(symbols)
        }

    def read_global_rates(self):
        return build_global_rates(fx_rate=FX)


def test_get_total_portfolio_combines_accounts():
    """Two accounts (one USD-denominated) combine into a single TOTAL portfolio:
    shared symbols keep one account-attributed holding per account, cash/flows
    CAD-normalize, weights use the combined total, and per-account slices are
    attached."""
    one_year_ago = date.today().replace(year=date.today().year - 1)
    acc_a = SimpleNamespace(
        open_positions=[_equity_lot("AAPL", qty=5, book=500.0, account="ACC-A")],
        cash_balance=100.0,
        external_cash_flows=[_contribution(1000.0, one_year_ago)],
    )
    acc_b = SimpleNamespace(
        open_positions=[
            _equity_lot("AAPL", qty=5, book=600.0, account="ACC-B"),
            _equity_lot("MSFT", qty=2, book=400.0, account="ACC-B"),
        ],
        cash_balance=50.0,
        external_cash_flows=[],
    )
    account_man = FakeMultiAccountManager(
        entities=[
            _entity("id-a", "ACC-A", currency=Currency.CAD),
            _entity("id-b", "ACC-B", currency=Currency.USD, type="RRSP"),
        ],
        accounts_by_number={"ACC-A": acc_a, "ACC-B": acc_b},
    )
    market_man = RealSecurityMarketManager()
    manager = PortfolioManager(market_man=market_man, account_man=account_man)

    snap = asyncio.run(manager.get_total_portfolio())

    # One consolidated, deduped securities fetch over the symbol union
    assert len(market_man.calls) == 1
    assert sorted(market_man.calls[0]) == ["AAPL", "MSFT"]

    assert snap.summary.id == "TOTAL"
    # One holding per account and symbol, keyed "account|symbol"
    assert set(snap.holdings) == {"ACC-A|AAPL", "ACC-B|AAPL", "ACC-B|MSFT"}
    assert snap.holdings["ACC-A|AAPL"].account == "ACC-A"
    assert snap.holdings["ACC-B|AAPL"].account == "ACC-B"
    # Per-account lots stay separate — no blended qty/ACB
    assert snap.holdings["ACC-A|AAPL"].open_qty == 5
    assert snap.holdings["ACC-A|AAPL"].book_value == pytest.approx(500.0)
    assert snap.holdings["ACC-B|AAPL"].open_qty == 5
    assert snap.holdings["ACC-B|AAPL"].book_value == pytest.approx(600.0)
    assert snap.summary.open_positions == ["AAPL", "MSFT"]

    # Cash: 100 CAD + 50 USD × fx
    assert snap.summary.cash_balance == pytest.approx(100.0 + 50.0 * FX)

    # Market values: all quotes USD close=110 → per share 110 × fx
    aapl_mv = 10 * 110.0 * FX
    msft_mv = 2 * 110.0 * FX
    total_value = aapl_mv + msft_mv + 100.0 + 50.0 * FX
    assert snap.summary.total_value == pytest.approx(total_value)
    aapl_weight = (
        snap.holdings["ACC-A|AAPL"].weight + snap.holdings["ACC-B|AAPL"].weight
    )
    assert aapl_weight == pytest.approx(aapl_mv / total_value)

    # Pooled MWRR over the union of external flows
    assert snap.summary.net_investment == pytest.approx(1000.0)
    assert snap.summary.mwrr > 0.0

    # Per-account slices reconcile to the total
    assert [s.id for s in snap.accounts] == ["id-a", "id-b"]
    slice_a, slice_b = snap.accounts
    assert slice_a.label == "TFSA #ACC-A"
    assert slice_b.label == "RRSP #ACC-B"
    assert slice_a.total_value == pytest.approx(5 * 110.0 * FX + 100.0)
    assert slice_b.total_value == pytest.approx(5 * 110.0 * FX + msft_mv + 50.0 * FX)
    assert slice_a.total_value + slice_b.total_value == pytest.approx(total_value)
    assert slice_a.weight + slice_b.weight == pytest.approx(1.0)
    assert slice_b.cash_balance == pytest.approx(50.0 * FX)

    # PORTF metrics/indicators built over the combined holdings
    assert snap.metrics.symbol == "PORTF"
    assert len(snap.indicators) > 0
    assert snap.correlation_matrix is not None


def test_get_total_portfolio_no_accounts_returns_empty_snapshot():
    manager = PortfolioManager(
        market_man=RealSecurityMarketManager(),
        account_man=FakeMultiAccountManager(entities=[], accounts_by_number={}),
    )

    snap = asyncio.run(manager.get_total_portfolio())

    assert snap.summary.id == "TOTAL"
    assert snap.summary.total_value == 0.0
    assert snap.holdings == {}
    assert snap.accounts == []
    assert snap.summary.mwrr == 0.0
