from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.backend.domain.analytics.security import compute_return_statistics

from src.backend.domain.analytics.allocation import (
    DIMENSIONS,
    calc_account_mix,
    calc_breakdown,
    calc_concentration,
    calc_risk_contribution,
    calc_symbol_weights,
)


def _row(symbol: str, value: float, **overrides) -> dict:
    row = {
        "symbol": symbol,
        "name": f"{symbol} Inc",
        "value": value,
        "is_option": False,
        "asset_type": "Stock",
        "instrument": "Equity",
        "sector": "Technology",
        "country": "US",
        "currency": "USD",
        "account": "ACC-A",
    }
    row.update(overrides)
    return row


def _cash(value: float, currency: str = "CAD", account: str = "ACC-A") -> dict:
    return _row(
        "CASH",
        value,
        name="Cash",
        asset_type="Cash",
        instrument="Cash",
        sector="Cash",
        country="Cash",
        currency=currency,
        account=account,
    )


def _rows(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def test_breakdown_shares_sum_to_one_and_sort_descending():
    rows = _rows(
        _row("AAPL", 600.0),
        _row("XIU.TO", 300.0, asset_type="ETF", currency="CAD"),
        _cash(100.0),
    )

    by_type = calc_breakdown(rows, "asset_type")

    assert [s["label"] for s in by_type] == ["Stock", "ETF", "Cash"]
    assert [s["weight"] for s in by_type] == pytest.approx([0.6, 0.3, 0.1])
    for dimension in DIMENSIONS:
        slices = calc_breakdown(rows, dimension)
        assert sum(s["weight"] for s in slices) == pytest.approx(1.0)
        assert sum(s["market_value"] for s in slices) == pytest.approx(1000.0)


def test_breakdown_drops_zero_value_labels_and_handles_empty():
    rows = _rows(
        _row("AAPL", 500.0),
        _row("AAPL", 0.0, instrument="Call Option", is_option=True),
    )

    assert [s["label"] for s in calc_breakdown(rows, "instrument")] == ["Equity"]
    assert calc_breakdown(_rows(_row("AAPL", 0.0)), "sector") == []


def test_symbol_weights_roll_up_accounts_and_options_and_exclude_cash():
    rows = _rows(
        _row("AAPL", 400.0, account="ACC-A"),
        _row("AAPL", 100.0, account="ACC-B"),
        _row("AAPL", 100.0, instrument="Call Option", is_option=True),
        _row("MSFT", 200.0),
        _cash(200.0),
    )

    weights = calc_symbol_weights(rows)

    assert [w["symbol"] for w in weights] == ["AAPL", "MSFT"]
    aapl = weights[0]
    assert aapl["market_value"] == pytest.approx(600.0)
    assert aapl["shares_value"] == pytest.approx(500.0)
    assert aapl["options_value"] == pytest.approx(100.0)
    assert aapl["weight"] == pytest.approx(0.6)
    assert weights[1]["weight"] == pytest.approx(0.2)


def test_concentration_on_known_weights():
    c = calc_concentration([40.0, 30.0, 20.0, 10.0])

    assert c["holdings"] == 4
    assert c["top1"] == pytest.approx(0.4)
    assert c["top5"] == pytest.approx(1.0)
    assert c["hhi"] == pytest.approx(0.30)
    assert c["effective_n"] == pytest.approx(1 / 0.30)


def test_concentration_equal_weights_and_empty():
    assert calc_concentration([1.0] * 8)["effective_n"] == pytest.approx(8.0)
    assert calc_concentration([])["holdings"] == 0
    assert calc_concentration([])["effective_n"] == 0.0


def _securities(
    seed: int, vols: dict[str, float], n: int = 120, short: dict[str, int] | None = None
) -> list[SimpleNamespace]:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2025-01-01", periods=n, freq="B")
    out = []
    for symbol, vol in vols.items():
        closes = pd.DataFrame(
            {"close": 100.0 * np.cumprod(1.0 + rng.normal(0.0, vol, n))}, index=index
        )
        keep = (short or {}).get(symbol, n)
        out.append(
            SimpleNamespace(
                quote=SimpleNamespace(symbol=symbol), indicators_df=closes.tail(keep)
            )
        )
    return out


def test_risk_contribution_sums_to_one_and_volatile_asset_dominates():
    stats = compute_return_statistics(_securities(7, {"CALM": 0.002, "WILD": 0.03}))

    result = calc_risk_contribution(
        {"CALM": 500.0, "WILD": 500.0}, stats.covariance, stats.observations
    )

    by_symbol = {r["symbol"]: r for r in result}
    assert by_symbol["CALM"]["weight"] == pytest.approx(0.5)
    assert sum(r["risk_share"] for r in result) == pytest.approx(1.0)
    assert by_symbol["WILD"]["risk_share"] > 0.9


def test_risk_contribution_short_history_is_none_not_zero():
    stats = compute_return_statistics(
        _securities(3, {"OLD": 0.01, "NEW": 0.01}, short={"NEW": 10})
    )

    result = calc_risk_contribution(
        {"OLD": 700.0, "NEW": 300.0}, stats.covariance, stats.observations
    )

    by_symbol = {r["symbol"]: r for r in result}
    assert by_symbol["NEW"]["risk_share"] is None
    assert by_symbol["NEW"]["weight"] == pytest.approx(0.3)
    assert by_symbol["OLD"]["risk_share"] == pytest.approx(1.0)


def test_risk_contribution_without_holdings_is_empty():
    assert calc_risk_contribution({}, pd.DataFrame(), {}) == []


def test_risk_contribution_agrees_with_correlation_matrix():
    """Risk shares rebuilt from the correlation matrix and each symbol's own
    volatility match the ones from the shared covariance."""
    stats = compute_return_statistics(
        _securities(11, {"AAA": 0.01, "BBB": 0.02, "CCC": 0.015})
    )
    values = {"AAA": 500.0, "BBB": 300.0, "CCC": 200.0}

    result = calc_risk_contribution(values, stats.covariance, stats.observations)

    symbols = list(values)
    w = np.array([values[s] for s in symbols]) / sum(values.values())
    sd = np.sqrt(np.diag(stats.covariance.loc[symbols, symbols]))
    cov = stats.correlation.loc[symbols, symbols].to_numpy() * np.outer(sd, sd)
    expected = w * (cov @ w) / (w @ cov @ w)
    by_symbol = {r["symbol"]: r["risk_share"] for r in result}
    assert [by_symbol[s] for s in symbols] == pytest.approx(expected.tolist())


def test_account_mix_is_normalized_per_account():
    rows = _rows(
        _row("AAPL", 300.0, account="ACC-A"),
        _cash(100.0, account="ACC-A"),
        _row("XIU.TO", 500.0, asset_type="ETF", account="ACC-B"),
    )

    mix = calc_account_mix(rows)

    a = {m["label"]: m["weight"] for m in mix if m["account"] == "ACC-A"}
    b = {m["label"]: m["weight"] for m in mix if m["account"] == "ACC-B"}
    assert a == pytest.approx({"Stock": 0.75, "Cash": 0.25})
    assert b == pytest.approx({"ETF": 1.0})


def test_account_mix_empty_for_single_account():
    assert calc_account_mix(_rows(_row("AAPL", 300.0), _cash(100.0))) == []


def test_symbol_weights_report_fixed_income_separately_from_shares():
    rows = _rows(
        _row("AAPL", 600.0),
        _row(
            "GIC-5.00-20241107",
            400.0,
            asset_type="Fixed Income",
            instrument="Fixed Income",
            sector="Fixed Income",
            country="Fixed Income",
            currency="CAD",
        ),
    )

    by_symbol = {r["symbol"]: r for r in calc_symbol_weights(rows)}

    gic = by_symbol["GIC-5.00-20241107"]
    assert gic["fixed_income_value"] == pytest.approx(400.0)
    assert gic["shares_value"] == pytest.approx(0.0)
    assert by_symbol["AAPL"]["fixed_income_value"] == 0.0
    assert by_symbol["AAPL"]["shares_value"] == pytest.approx(600.0)


def test_risk_contribution_steady_holding_has_zero_risk_not_none():
    stats = compute_return_statistics(_securities(5, {"STOCK": 0.02}))

    result = calc_risk_contribution(
        {"STOCK": 600.0, "GIC-5.00-20241107": 400.0},
        stats.covariance,
        stats.observations,
        steady={"GIC-5.00-20241107"},
    )

    by_symbol = {r["symbol"]: r for r in result}
    assert by_symbol["GIC-5.00-20241107"]["weight"] == pytest.approx(0.4)
    assert by_symbol["GIC-5.00-20241107"]["risk_share"] == 0.0
    assert by_symbol["STOCK"]["risk_share"] == pytest.approx(1.0)
