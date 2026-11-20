from datetime import datetime, timezone

import numpy as np
import pandas as pd

from frontend.widgets.treemaps import (
    COLOR_REL_VOLUME,
    REL_VOLUME_COLOR_MAX,
    compact_number,
    render_treemap_intraday,
)

GROUPS = ["region", "group_label"]


def _frame(relative_volume: list[float] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "name": ["A", "B", "C"],
            "close": [10.0, 20.0, 30.0],
            "currency": "USD",
            "change": [0.1, -0.2, 0.0],
            "change_percent": [0.01, -0.01, 0.0],
            "volume": [100.0, 200.0, 0.0],
            "timestamp": datetime(2026, 1, 5, tzinfo=timezone.utc),
            "region": "US",
            "group_label": "Core",
        },
        index=pd.Index(["AAA", "BBB", "CCC"], name="symbol"),
    )
    if relative_volume is not None:
        df["relative_volume"] = relative_volume
    return df


def _leaf_colors(fig) -> dict[str, float]:
    trace = fig.data[0]
    return dict(zip(trace.labels, trace.marker.colors))


def test_default_colour_is_change_percent_diverging():
    fig = render_treemap_intraday(_frame([1.0, 2.0, np.nan]), group_cols=GROUPS)

    assert fig.layout.coloraxis.cmid == 0
    assert _leaf_colors(fig)["BBB"] == -0.01


def test_relative_volume_colour_is_sequential_and_clipped():
    fig = render_treemap_intraday(
        _frame([1.5, 7.0, np.nan]), group_cols=GROUPS, color_by=COLOR_REL_VOLUME
    )

    axis = fig.layout.coloraxis
    assert (axis.cmin, axis.cmax) == (0, REL_VOLUME_COLOR_MAX)
    assert axis.cmid is None
    colors = _leaf_colors(fig)
    assert colors["AAA"] == 1.5
    assert colors["BBB"] == REL_VOLUME_COLOR_MAX
    assert colors["CCC"] == 0.0


def test_tile_text_shows_the_multiple_only_when_known():
    fig = render_treemap_intraday(_frame([1.5, 7.0, np.nan]), group_cols=GROUPS)
    text = dict(zip(fig.data[0].labels, (c[0] for c in fig.data[0].customdata)))

    assert "Vol. 100 · 1.5×<br>" in text["AAA"]
    assert "×" not in text["CCC"]


def test_compact_number():
    assert compact_number(950) == "950"
    assert compact_number(1_234) == "1.2K"
    assert compact_number(999_950) == "1.0M"
    assert compact_number(2_627_000) == "2.6M"
    assert compact_number(71_300_000_000) == "71.3B"
    assert compact_number(float("nan")) == "N/A"


def test_frame_without_relative_volume_still_renders():
    fig = render_treemap_intraday(_frame(), group_cols=GROUPS)

    assert "×" not in fig.data[0].customdata[0][0]
