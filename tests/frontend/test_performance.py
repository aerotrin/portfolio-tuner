"""Tests for the Performance tab's statistic formatters.

Portfolio metrics arrive as None/NaN when holdings have too little price
history (e.g. a newly listed security), so the formatters must not raise.
"""

import pytest

from frontend.widgets.performance import MISSING_STAT, _fmt_stat, _fmt_stat_delta


@pytest.mark.parametrize("missing", [None, float("nan")])
def test_fmt_stat_missing_value_renders_dash(missing):
    assert _fmt_stat(missing, ".1%") == MISSING_STAT


def test_fmt_stat_formats_present_value():
    assert _fmt_stat(0.1234, ".1%") == "12.3%"
    assert _fmt_stat(1.23456, ".3f") == "1.235"


@pytest.mark.parametrize(
    ("value", "benchmark"),
    [(None, 0.1), (0.1, None), (float("nan"), 0.1), (None, None)],
)
def test_fmt_stat_delta_missing_side_returns_none(value, benchmark):
    assert _fmt_stat_delta(value, benchmark, "+.1%") is None


def test_fmt_stat_delta_formats_difference():
    assert _fmt_stat_delta(0.15, 0.10, "+.1%") == "+5.0%"
    assert _fmt_stat_delta(0.05, 0.10, "+.1%") == "-5.0%"
