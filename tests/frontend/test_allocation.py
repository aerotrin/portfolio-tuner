"""Tests for the Allocation tab's frame and chart builders."""

import json

import pytest

from frontend.settings import (
    CHART_CATEGORICAL_LIGHT,
    CHART_OTHER_COLOR,
    DONUT_CASH_COLOR,
)
from frontend.widgets.allocation import (
    _account_mix_frame,
    _breakdown_frame,
    _build_account_mix_bar,
    _build_breakdown_donut,
    _build_ranked_bar,
    _build_risk_bar,
    _color_scale,
    _holding_labels,
    _holdings_frame,
    _risk_frame,
)


def _slice(label: str, value: float, total: float = 1000.0) -> dict:
    return {"label": label, "market_value": value, "weight": value / total}


def _symbol(symbol: str, value: float, options: float = 0.0) -> dict:
    return {
        "symbol": symbol,
        "name": f"{symbol} Inc",
        "market_value": value,
        "weight": value / 1000.0,
        "shares_value": value - options,
        "options_value": options,
    }


def test_breakdown_frame_puts_cash_last_and_maps_labels():
    df = _breakdown_frame(
        [_slice("Cash", 500.0), _slice("111", 300.0), _slice("222", 200.0)],
        labels={"111": "TFSA #111"},
    )

    assert df["label"].tolist() == ["TFSA #111", "222", "Cash"]
    assert df["weight"].sum() == pytest.approx(1.0)


def test_breakdown_frame_folds_extra_categories_into_other():
    slices = [_slice(f"S{i}", 100.0 - i) for i in range(6)] + [_slice("Cash", 50.0)]

    df = _breakdown_frame(slices, max_named=4)

    assert df["label"].tolist() == ["S0", "S1", "S2", "S3", "Other", "Cash"]
    other = df[df["label"] == "Other"].iloc[0]
    assert other["market_value"] == pytest.approx(96.0 + 95.0)


def test_breakdown_frame_empty():
    assert _breakdown_frame([]).empty


def test_holdings_frame_top_n_other_and_cash():
    by_symbol = [_symbol(f"S{i}", 100.0 - i) for i in range(5)]

    df = _holdings_frame(by_symbol, _slice("Cash", 40.0), top_n=3)

    assert df["label"].tolist() == ["S0", "S1", "S2", "Other", "Cash"]
    assert df["kind"].tolist() == ["Holding"] * 3 + ["Other", "Cash"]
    assert df.loc[3, "market_value"] == pytest.approx(97.0 + 96.0)
    assert df.loc[3, "name"] == "2 smaller holdings"


def _fixed_income(symbol: str, name: str, value: float) -> dict:
    return {
        **_symbol(symbol, value),
        "name": name,
        "shares_value": 0.0,
        "fixed_income_value": value,
    }


def test_fixed_income_is_labelled_by_name_not_key():
    by_symbol = [
        _fixed_income("GIC-2.45-20261209-ac3b", "GIC 2.45% Dec 09 2026", 500.0),
        _symbol("AAA", 300.0),
    ]
    risk = [
        {"symbol": "GIC-2.45-20261209-ac3b", "weight": 0.6, "risk_share": 0.0},
        {"symbol": "AAA", "weight": 0.4, "risk_share": 1.0},
    ]

    labels = _holding_labels(by_symbol)
    holdings = _holdings_frame(by_symbol, None)
    risk_df, _ = _risk_frame(risk, labels=labels)

    assert holdings["label"].tolist() == ["GIC 2.45% Dec 09 2026", "AAA"]
    assert risk_df["symbol"].unique().tolist() == ["GIC 2.45% Dec 09 2026", "AAA"]


def test_fixed_income_sharing_a_name_keeps_its_key():
    by_symbol = [
        _fixed_income("GIC-2.45-20261209-ac3b", "GIC 2.45% Dec 09 2026", 500.0),
        _fixed_income("GIC-2.45-20261209-9f10", "GIC 2.45% Dec 09 2026", 300.0),
    ]

    assert _holding_labels(by_symbol) == {}


def test_holdings_frame_cash_only():
    df = _holdings_frame([], _slice("Cash", 40.0))

    assert df["label"].tolist() == ["Cash"]


def test_risk_frame_separates_unmeasured_symbols():
    risk = [
        {"symbol": "AAA", "weight": 0.6, "risk_share": 0.8},
        {"symbol": "NEW", "weight": 0.1, "risk_share": None},
        {"symbol": "BBB", "weight": 0.3, "risk_share": 0.2},
    ]

    df, unmeasured = _risk_frame(risk)

    assert unmeasured == ["NEW"]
    assert df["symbol"].tolist() == ["AAA", "AAA", "BBB", "BBB"]
    assert df["measure"].tolist() == ["Weight", "Risk share"] * 2
    assert df["value"].tolist() == pytest.approx([0.6, 0.8, 0.3, 0.2])


def test_account_mix_frame_maps_account_labels():
    mix = [
        {"account": "111", "label": "Stock", "market_value": 10.0, "weight": 1.0},
    ]

    df = _account_mix_frame(mix, {"111": "TFSA #••••"})

    assert df["account"].tolist() == ["TFSA #••••"]


def test_color_scale_is_stable_per_label_with_grey_cash_and_other():
    first = _color_scale(["Stock", "ETF", "Other", "Cash"], dark=False)
    reordered = _color_scale(["ETF", "Cash", "Stock", "Other"], dark=False)

    a = dict(zip(first.domain, first.range))
    b = dict(zip(reordered.domain, reordered.range))
    assert a == b
    assert a["ETF"] == CHART_CATEGORICAL_LIGHT[0]
    assert a["Cash"] == DONUT_CASH_COLOR
    assert a["Other"] == CHART_OTHER_COLOR


@pytest.mark.parametrize("hide_balances", [True, False])
def test_charts_expose_dollar_values_only_when_balances_are_shown(hide_balances):
    breakdown = _breakdown_frame([_slice("Stock", 900.0), _slice("Cash", 100.0)])
    holdings = _holdings_frame([_symbol("AAA", 900.0, 100.0)], _slice("Cash", 100.0))
    mix = _account_mix_frame(
        [
            {"account": "111", "label": "Stock", "market_value": 900.0, "weight": 1.0},
            {"account": "222", "label": "Cash", "market_value": 100.0, "weight": 1.0},
        ]
    )
    charts = [
        _build_breakdown_donut(breakdown, "Asset type", False, hide_balances),
        _build_ranked_bar(holdings, False, hide_balances),
        _build_account_mix_bar(mix, False, hide_balances),
    ]

    for chart in charts:
        spec = chart.to_dict()
        encodings = [layer["encoding"] for layer in spec.get("layer", [spec])]
        tooltip_fields = {
            t["field"] for encoding in encodings for t in encoding.get("tooltip", [])
        }
        has_values = bool(
            tooltip_fields & {"market_value", "shares_value", "options_value"}
        )
        assert has_values is not hide_balances


def test_risk_chart_builds_a_valid_spec():
    df, _ = _risk_frame([{"symbol": "AAA", "weight": 1.0, "risk_share": 1.0}])

    spec = _build_risk_bar(df, dark=True).to_dict()

    assert spec["encoding"]["xOffset"]["field"] == "measure"
    json.dumps(spec)
