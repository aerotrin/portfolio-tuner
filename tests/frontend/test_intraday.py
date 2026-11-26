import pandas as pd

from frontend.widgets.intraday import (
    _drill_filter,
    _next_level,
    _quotes_heading,
    _sort_quotes,
)

TOP = "ETF Market"


def _sub() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "region": ["US", "US", "US", "Canada", "Canada"],
            "group_label": ["Tech", "Tech", "Bonds/Credit", "Banks", "Tech"],
        },
        index=pd.Index(["QQQ", "XLK", "LQD", "ZEB", "QQQ"], name="symbol"),
    )


def test_no_selection_returns_everything():
    assert len(_drill_filter(_sub(), TOP, None)[0]) == 5


def test_root_returns_everything():
    assert len(_drill_filter(_sub(), TOP, TOP)[0]) == 5


def test_region_tile():
    out, _ = _drill_filter(_sub(), TOP, f"{TOP}/US")
    assert list(out.index) == ["QQQ", "XLK", "LQD"]


def test_group_tile():
    out, _ = _drill_filter(_sub(), TOP, f"{TOP}/US/Tech")
    assert list(out.index) == ["QQQ", "XLK"]


def test_symbol_tile_is_one_row():
    out, _ = _drill_filter(_sub(), TOP, f"{TOP}/US/Tech/XLK")
    assert list(out.index) == ["XLK"]


def test_symbol_in_two_groups_matches_only_clicked_parent():
    out, _ = _drill_filter(_sub(), TOP, f"{TOP}/Canada/Tech/QQQ")
    assert len(out) == 1
    assert out["region"].iloc[0] == "Canada"


def test_group_label_containing_slash():
    out, _ = _drill_filter(_sub(), TOP, f"{TOP}/US/Bonds/Credit")
    assert list(out.index) == ["LQD"]


def test_prefix_does_not_match_partial_segment():
    out, _ = _drill_filter(_sub(), TOP, f"{TOP}/U")
    assert len(out) == 5


def test_stale_id_returns_everything():
    assert len(_drill_filter(_sub(), TOP, f"{TOP}/Europe/Autos")[0]) == 5


def test_path_parts_for_heading():
    _, parts = _drill_filter(_sub(), TOP, f"{TOP}/US/Bonds/Credit")
    assert parts == ["US", "Bonds/Credit"]
    assert _drill_filter(_sub(), TOP, TOP)[1] == []


def test_click_new_tile_zooms_into_it():
    assert _next_level(_sub(), TOP, None, f"{TOP}/US/Tech") == f"{TOP}/US/Tech"
    assert _next_level(_sub(), TOP, f"{TOP}/US/Tech", f"{TOP}/US") == f"{TOP}/US"


def test_click_current_tile_walks_up_to_parent():
    sub = _sub()
    assert _next_level(sub, TOP, f"{TOP}/US/Tech/XLK", f"{TOP}/US/Tech/XLK") == (
        f"{TOP}/US/Tech"
    )
    assert _next_level(sub, TOP, f"{TOP}/US/Tech", f"{TOP}/US/Tech") == f"{TOP}/US"
    assert _next_level(sub, TOP, f"{TOP}/US", f"{TOP}/US") is None


def test_walk_up_with_slash_in_group_label():
    level = f"{TOP}/US/Bonds/Credit"
    assert _next_level(_sub(), TOP, level, level) == f"{TOP}/US"


def test_root_or_no_click_is_root_level():
    assert _next_level(_sub(), TOP, f"{TOP}/US", TOP) is None
    assert _next_level(_sub(), TOP, f"{TOP}/US", None) is None


def test_drill_then_walk_back_follows_the_prefiltered_set():
    prefiltered = _sub()[_sub()["group_label"] == "Tech"]
    level = _next_level(prefiltered, TOP, None, f"{TOP}/US/Tech")
    drilled, parts = _drill_filter(prefiltered, TOP, level)
    assert list(drilled.index) == ["QQQ", "XLK"]
    assert parts == ["US", "Tech"]

    level = _next_level(prefiltered, TOP, level, f"{TOP}/US/Tech")
    up, parts = _drill_filter(prefiltered, TOP, level)
    assert list(up.index) == ["QQQ", "XLK"]
    assert parts == ["US"]

    level = _next_level(prefiltered, TOP, level, f"{TOP}/US")
    back, parts = _drill_filter(prefiltered, TOP, level)
    assert back.equals(prefiltered)
    assert parts == []


def test_quotes_heading():
    assert _quotes_heading("ETF Quotes", [], "") == "ETF Quotes"
    assert _quotes_heading("ETF Quotes", [], "US / Tech") == "ETF Quotes · US / Tech"
    assert (
        _quotes_heading("ETF Quotes", ["Fixed Income", "Forex"], "US")
        == "ETF Quotes (Fixed Income, Forex) · US"
    )


# Sort ----------------------------------------------------------------------------


def _quotes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "change_percent": [0.03, -0.01, 0.02, 0.01],
            "relative_volume": [0.5, 2.5, None, 1.2],
            "dollar_volume": [9e6, 2e6, None, 5e6],
        },
        index=pd.Index(["AAA", "BBB", "IDX", "CCC"], name="symbol"),
    )


def test_sort_by_change_percent():
    out = _sort_quotes(_quotes(), "change_percent")
    assert list(out.index) == ["AAA", "IDX", "CCC", "BBB"]


def test_sort_by_relative_volume_puts_missing_last():
    out = _sort_quotes(_quotes(), "relative_volume")
    assert list(out.index) == ["BBB", "CCC", "AAA", "IDX"]


def test_sort_falls_back_to_change_percent_without_the_metric():
    out = _sort_quotes(_quotes().drop(columns="relative_volume"), "relative_volume")
    assert list(out.index) == ["AAA", "IDX", "CCC", "BBB"]


def test_sort_by_dollar_volume_puts_missing_last():
    out = _sort_quotes(_quotes(), "dollar_volume")
    assert list(out.index) == ["AAA", "CCC", "BBB", "IDX"]
