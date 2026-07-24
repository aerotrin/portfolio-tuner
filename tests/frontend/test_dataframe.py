import numpy as np
import pandas as pd
import pytest

from frontend.shared.dataframe import compute_correlation_matrix
from frontend.shared.settings import TRADING_DAYS_PER_YEAR


def _closes(data: dict[str, list[float]], periods: int) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="B")
    return pd.DataFrame(data, index=index)


def test_perfectly_correlated_and_inverse_pairs():
    n = 100
    rng = np.random.default_rng(42)
    r = rng.normal(0, 0.01, n)
    # Daily returns r, 2r, and -r give exact pairwise correlations of +1 and -1.
    closes = _closes(
        {
            "AAA": (100 * np.cumprod(1 + r)).tolist(),
            "BBB": (100 * np.cumprod(1 + 2 * r)).tolist(),
            "CCC": (100 * np.cumprod(1 - r)).tolist(),
        },
        n,
    )

    corr = compute_correlation_matrix(closes)

    assert corr.loc["AAA", "BBB"] == pytest.approx(1.0)
    assert corr.loc["AAA", "CCC"] == pytest.approx(-1.0)


def test_symbols_filter_restricts_columns_and_ignores_unknown():
    n = 50
    rng = np.random.default_rng(42)
    closes = _closes(
        {s: (100 + rng.standard_normal(n).cumsum()).tolist() for s in "ABC"}, n
    )

    corr = compute_correlation_matrix(closes, symbols=["A", "B", "ZZZ"])

    assert sorted(corr.columns) == ["A", "B"]
    assert sorted(corr.index) == ["A", "B"]


def test_only_trailing_window_used():
    extra = 100
    n = TRADING_DAYS_PER_YEAR + extra
    rng = np.random.default_rng(7)
    x = 100 + rng.standard_normal(n).cumsum()
    # Inside the trailing window Y moves with X; before it, Y moves against X.
    y = np.concatenate([-x[:extra] + 300, x[extra:]])
    closes = _closes({"X": x.tolist(), "Y": y.tolist()}, n)

    corr = compute_correlation_matrix(closes)

    assert corr.loc["X", "Y"] == pytest.approx(1.0)


def test_constant_price_column_dropped():
    n = 50
    rng = np.random.default_rng(1)
    closes = _closes(
        {
            "A": (100 + rng.standard_normal(n).cumsum()).tolist(),
            "B": (100 + rng.standard_normal(n).cumsum()).tolist(),
            "FLAT": [100.0] * n,
        },
        n,
    )

    corr = compute_correlation_matrix(closes)

    assert "FLAT" not in corr.columns
    assert "FLAT" not in corr.index
    assert sorted(corr.columns) == ["A", "B"]


def test_interior_nans_forward_filled():
    n = 60
    rng = np.random.default_rng(3)
    r = rng.normal(0, 0.01, n)
    a = 100 * np.cumprod(1 + r)
    a[10:15] = np.nan
    closes = _closes({"A": a.tolist(), "B": (100 * np.cumprod(1 + 2 * r)).tolist()}, n)

    corr = compute_correlation_matrix(closes)

    # A stays in the matrix (ffill bridges the gap) and remains strongly correlated.
    assert not np.isnan(corr.loc["A", "B"])
    assert corr.loc["A", "B"] > 0.8
