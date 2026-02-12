from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from backend.domain.aggregates.portfolio import Portfolio
from backend.domain.aggregates.security import Security
from backend.domain.entities.account import Category, OpenLot
from backend.domain.entities.security import GlobalRates, Profile, Quote, SecurityType


def _make_security(
    symbol: str,
    currency: str,
    close: float,
    change: float,
    change_percent: float,
) -> Security:
    security = Security.__new__(Security)
    security.quote = Quote(
        symbol=symbol,
        name=f"{symbol} Inc.",
        exchange="TEST",
        open=close,
        high=close,
        low=close,
        close=close,
        currency=currency,
        volume=1_000,
        change=change,
        change_percent=change_percent,
        previousClose=close - change,
        timestamp=datetime(2024, 1, 1, 16, 0, 0),
    )
    security.profile = Profile(
        symbol=symbol,
        name=f"{symbol} Inc.",
        date=datetime(2024, 1, 1),
        type=SecurityType.STOCK,
        exchange="TEST",
        currency=currency,
    )
    security.indicators_df = pd.DataFrame(
        {
            "close": [close],
            "daily_return": [0.0],
        },
        index=pd.to_datetime(["2024-01-01"]),
    )
    return security


def _stub_portfolio_analytics(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.domain.aggregates.portfolio as portfolio_module

    monkeypatch.setattr(
        portfolio_module,
        "compute_portfolio_timeseries_indicators",
        lambda _securities, _weights: [
            pd.DataFrame(
                {
                    "symbol": ["PORTF"],
                    "close": [1.0],
                    "close_norm": [1.0],
                    "daily_return": [0.0],
                    "ema12": [1.0],
                    "ema26": [1.0],
                    "ema100": [1.0],
                    "macd_12_26": [0.0],
                    "macd_signal_9": [0.0],
                    "macd_histogram": [0.0],
                    "rsi": [50.0],
                    "rsi_signal_5": [50.0],
                },
                index=pd.to_datetime(["2024-01-01"]),
            )
        ],
    )
    monkeypatch.setattr(
        portfolio_module,
        "compute_performance_metrics",
        lambda _indicators_df, _rf_rate: pd.DataFrame(
            [{"return5D": 0.0}],
            index=pd.Index(["PORTF"], name="symbol"),
        ),
    )


def test_portfolio_build_holdings_summary_and_contributions(monkeypatch: pytest.MonkeyPatch):
    _stub_portfolio_analytics(monkeypatch)

    import backend.domain.aggregates.portfolio as portfolio_module

    monkeypatch.setattr(
        portfolio_module,
        "compute_correlation_matrix",
        lambda _securities: pd.DataFrame(),
    )

    securities = {
        "EQUSD": _make_security("EQUSD", "USD", close=50.0, change=2.0, change_percent=0.04),
        "EQCAD": _make_security("EQCAD", "CAD", close=20.0, change=-1.0, change_percent=-0.05),
        "CALLUSD": _make_security("CALLUSD", "USD", close=50.0, change=1.0, change_percent=0.02),
        "PUTCAD": _make_security("PUTCAD", "CAD", close=20.0, change=-0.5, change_percent=-0.02),
    }

    positions = [
        OpenLot(
            symbol="EQUSD",
            category=Category.EQUITY,
            open_date=date.today() - timedelta(days=90),
            open_qty=10,
            acb_per_sh=50.0,
            book_value=500.0,
        ),
        OpenLot(
            symbol="EQCAD",
            category=Category.EQUITY,
            open_date=date.today() - timedelta(days=60),
            open_qty=5,
            acb_per_sh=20.0,
            book_value=100.0,
        ),
        OpenLot(
            symbol="CALLUSD",
            category=Category.CALL_OPTION,
            option_osi="AAPL_CALL_ITM",
            open_date=date.today() - timedelta(days=30),
            option_expiry=date.today() + timedelta(days=10),
            option_strike=40.0,
            open_qty=1,
            acb_per_sh=750.0,
            book_value=600.0,
        ),
        OpenLot(
            symbol="PUTCAD",
            category=Category.PUT_OPTION,
            option_osi="SHOP_PUT_EXP",
            open_date=date.today() - timedelta(days=45),
            option_expiry=date.today() - timedelta(days=1),
            option_strike=30.0,
            open_qty=1,
            acb_per_sh=200.0,
            book_value=200.0,
        ),
    ]

    portfolio = Portfolio(
        id="acct-1",
        cash=500.0,
        positions=positions,
        securities=securities,
        rates=GlobalRates(rf_rate=0.0, fx_rate=1.25),
    )

    equity_usd = portfolio.holdings["EQUSD"]
    equity_cad = portfolio.holdings["EQCAD"]
    call_usd = portfolio.holdings["CALLUSD"]
    put_cad = portfolio.holdings["PUTCAD"]

    assert equity_usd.fx_rate == 1.25
    assert equity_usd.market_value == pytest.approx(625.0)
    assert equity_usd.book_value == pytest.approx(500.0)
    assert equity_usd.gain == pytest.approx(125.0)
    assert equity_usd.gain_pct == pytest.approx(0.25)

    assert equity_cad.fx_rate == 1.0
    assert equity_cad.market_value == pytest.approx(100.0)
    assert equity_cad.book_value == pytest.approx(100.0)
    assert equity_cad.gain == pytest.approx(0.0)
    assert equity_cad.gain_pct == pytest.approx(0.0)

    assert call_usd.fx_rate == 1.25
    assert call_usd.market_value == pytest.approx(1250.0)
    assert call_usd.option_value == pytest.approx(10.0)
    assert call_usd.option_expired is False
    assert call_usd.gain == pytest.approx(650.0)
    assert call_usd.gain_pct == pytest.approx(650.0 / 600.0)

    assert put_cad.fx_rate == 1.0
    assert put_cad.market_value == pytest.approx(0.0)
    assert put_cad.option_value == pytest.approx(0.0)
    assert put_cad.option_expired is True
    assert put_cad.gain == pytest.approx(-200.0)
    assert put_cad.gain_pct == pytest.approx(-1.0)

    assert portfolio.market_value == pytest.approx(1975.0)
    assert portfolio.book_value == pytest.approx(1400.0)
    assert portfolio.total_value == pytest.approx(2475.0)
    assert portfolio.cash_pct == pytest.approx(500.0 / 2475.0)
    assert portfolio.unrealized_gain == pytest.approx(575.0)
    assert portfolio.return_on_cost == pytest.approx(575.0 / 1400.0)
    assert portfolio.return_on_value == pytest.approx(575.0 / 2475.0)
    assert portfolio.pnl_intraday == pytest.approx(20.0)

    assert call_usd.weight == pytest.approx(1250.0 / 2475.0)
    assert call_usd.pnl_contribution == pytest.approx(650.0 / 2475.0)
    assert call_usd.intraday_contribution == pytest.approx(0.0)

    assert equity_usd.weight == pytest.approx(625.0 / 2475.0)
    assert equity_usd.pnl_contribution == pytest.approx(125.0 / 2475.0)
    assert equity_usd.intraday_contribution == pytest.approx(25.0 / 2475.0)


def test_build_correlation_matrix_dto_shape(monkeypatch: pytest.MonkeyPatch):
    _stub_portfolio_analytics(monkeypatch)

    import backend.domain.aggregates.portfolio as portfolio_module

    monkeypatch.setattr(
        portfolio_module,
        "compute_correlation_matrix",
        lambda _securities: pd.DataFrame(
            [[1.0, 0.35], [0.35, 1.0]],
            index=["AAPL", "SHOP"],
            columns=["AAPL", "SHOP"],
        ),
    )

    securities = {
        "EQUSD": _make_security("EQUSD", "USD", close=50.0, change=2.0, change_percent=0.04),
        "EQCAD": _make_security("EQCAD", "CAD", close=20.0, change=-1.0, change_percent=-0.05),
        "CALLUSD": _make_security("CALLUSD", "USD", close=50.0, change=1.0, change_percent=0.02),
        "PUTCAD": _make_security("PUTCAD", "CAD", close=20.0, change=-0.5, change_percent=-0.02),
    }
    positions = [
        OpenLot(
            symbol="EQUSD",
            category=Category.EQUITY,
            open_date=date.today() - timedelta(days=1),
            open_qty=1,
            acb_per_sh=10.0,
            book_value=10.0,
        )
    ]

    portfolio = Portfolio(
        id="acct-2",
        cash=0.0,
        positions=positions,
        securities=securities,
        rates=GlobalRates(rf_rate=0.0, fx_rate=1.25),
    )

    corr = portfolio.correlation_matrix
    assert corr.symbols == ["AAPL", "SHOP"]
    assert corr.entries is not None
    assert len(corr.entries) == 4

    first = corr.entries[0]
    assert first.row in {"AAPL", "SHOP"}
    assert first.col in {"AAPL", "SHOP"}
    assert isinstance(first.value, float)


def test_build_correlation_matrix_empty_securities_guard():
    portfolio = Portfolio(
        id="acct-3",
        cash=0.0,
        positions=[],
        securities={},
        rates=GlobalRates(rf_rate=0.0, fx_rate=1.0),
    )

    portfolio._build_correlation_matrix()

    assert portfolio.correlation_matrix.symbols is None
    assert portfolio.correlation_matrix.entries is None
