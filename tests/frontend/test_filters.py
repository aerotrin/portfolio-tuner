"""Tests for the pure selection logic behind the Performance tab group filter.

`_select` takes the raw selection as an argument rather than reading session
state, so these run without a Streamlit runtime.

Labels are deliberately non-unique here ("Core" under both US and Canada),
mirroring symbols.yml: a tile is a region plus a label.
"""

from frontend.shared.symbols_loader import SymbolGroup
from frontend.widgets.filters import (
    _is_narrowed,
    _select,
    _summary,
    drill_defaults,
    drill_state,
    facet_key,
    tile_options,
)

US_CORE = SymbolGroup(label="Core", type="Equity", region="US", symbols=("SPY", "VTI"))
US_SECTORS = SymbolGroup(
    label="Sectors", type="Equity", region="US", symbols=("XLK", "XLF")
)
US_CASH = SymbolGroup(label="Cash", type="Fixed Income", region="US", symbols=("BIL",))
US_CREDIT = SymbolGroup(
    label="Bonds/Credit", type="Fixed Income", region="US", symbols=("LQD",)
)
CA_CORE = SymbolGroup(label="Core", type="Equity", region="Canada", symbols=("XIC.TO",))
CA_SECTORS = SymbolGroup(
    label="Sectors", type="Equity", region="Canada", symbols=("XFN.TO",)
)
COMMODITY = SymbolGroup(
    label="Commodity", type="Commodity", region="Global", symbols=("GLD", "SPY")
)

# Canada before US in config order: options must still follow REGION_ORDER.
GROUPS = [CA_CORE, CA_SECTORS, US_CORE, US_SECTORS, US_CASH, US_CREDIT, COMMODITY]


def _run(selected=(), defaults=()):
    return _select(GROUPS, selected, defaults, key_prefix="test")


# Options -----------------------------------------------------------------------


def test_options_are_group_tiles_in_region_order():
    assert _run().options == (
        "US / Core",
        "US / Sectors",
        "US / Cash",
        "US / Bonds/Credit",
        "Canada / Core",
        "Canada / Sectors",
        "Global / Commodity",
    )


def test_a_region_is_not_an_option():
    assert _run(["US"]).selected == ()


def test_a_label_under_two_types_is_one_tile():
    twin = SymbolGroup(label="Core", type="Fixed Income", region="US", symbols=("AGG",))
    options = tile_options([US_CORE, twin])

    assert list(options) == ["US / Core"]
    assert options["US / Core"] == (US_CORE, twin)


def test_no_groups_yields_empty_everything():
    result = _select([], [], key_prefix="test")

    assert result.groups == () and result.symbols == () and result.options == ()


# Selection ---------------------------------------------------------------------


def test_empty_selection_means_every_group():
    result = _run()

    assert result.groups == tuple(GROUPS)
    assert result.symbols == (
        "BIL",
        "GLD",
        "LQD",
        "SPY",
        "VTI",
        "XFN.TO",
        "XIC.TO",
        "XLF",
        "XLK",
    )


def test_group_tile_selects_one_region_only():
    result = _run(["Canada / Core"])

    assert result.groups == (CA_CORE,)
    assert result.symbols == ("XIC.TO",)


def test_tiles_from_different_regions_combine():
    result = _run(["US / Sectors", "Canada / Sectors"])

    assert result.groups == (CA_SECTORS, US_SECTORS)
    assert result.symbols == ("XFN.TO", "XLF", "XLK")


def test_symbols_are_deduped_across_tiles():
    # SPY sits in both US Core and Global Commodity.
    result = _run(["US / Core", "Global / Commodity"])

    assert result.symbols == ("GLD", "SPY", "VTI")


def test_label_containing_a_slash_round_trips():
    result = _run(["US / Bonds/Credit"])

    assert result.groups == (US_CREDIT,)


def test_unknown_tile_is_dropped():
    result = _run(["Atlantis / Core", "US / Core"])

    assert result.selected == ("US / Core",)


def test_only_unknown_tiles_falls_back_to_all():
    result = _run(["Atlantis"])

    assert result.selected == ()
    assert result.groups == tuple(GROUPS)


def test_bare_string_is_treated_as_one_value():
    assert _run("Canada / Core").selected == ("Canada / Core",)


# Following the treemap ---------------------------------------------------------


def test_drill_state_reads_region_and_group_from_the_path():
    assert drill_state([], []) == {"types": [], "region": None, "group": None}
    assert drill_state([], ["US"])["region"] == "US"
    assert drill_state([], ["US"])["group"] is None
    assert drill_state([], ["US", "Core"])["group"] == "Core"


def test_drill_state_treats_a_symbol_tile_as_its_group():
    assert drill_state([], ["US", "Core", "SPY"]) == drill_state([], ["US", "Core"])


def test_drill_state_ignores_type_pick_order():
    assert drill_state(["Equity", "Commodity"], []) == drill_state(
        ["Commodity", "Equity"], []
    )


def test_unzoomed_map_defaults_to_the_first_group():
    for drill in (None, drill_state([], [])):
        assert drill_defaults(GROUPS, drill) == ("Canada / Core",)


def test_unzoomed_map_with_a_type_slice_selects_every_group_it_shows():
    drill = drill_state(["Equity"], [])

    assert drill_defaults(GROUPS, drill) == (
        "Canada / Core",
        "Canada / Sectors",
        "US / Core",
        "US / Sectors",
    )


def test_type_slice_matching_nothing_falls_back_to_the_first_group():
    assert drill_defaults(GROUPS, drill_state(["Crypto"], [])) == ("Canada / Core",)


def test_region_zoom_selects_every_group_in_the_region():
    assert drill_defaults(GROUPS, drill_state([], ["US"])) == (
        "US / Core",
        "US / Sectors",
        "US / Cash",
        "US / Bonds/Credit",
    )


def test_group_and_symbol_zoom_select_the_group_tile():
    for parts in (["Canada", "Core"], ["Canada", "Core", "XIC.TO"]):
        assert drill_defaults(GROUPS, drill_state([], parts)) == ("Canada / Core",)


def test_region_zoom_within_a_type_slice_names_the_groups_shown():
    drill = drill_state(["Fixed Income"], ["US"])

    assert drill_defaults(GROUPS, drill) == ("US / Cash", "US / Bonds/Credit")


def test_region_zoom_with_a_type_slice_missing_there_shows_the_whole_region():
    drill = drill_state(["Commodity"], ["Canada"])

    assert drill_defaults(GROUPS, drill) == ("Canada / Core", "Canada / Sectors")


def test_every_default_is_a_selectable_tile():
    options = tile_options(GROUPS)
    drills = [
        None,
        drill_state(["Commodity"], []),
        drill_state([], ["Global"]),
        drill_state(["Fixed Income"], ["US"]),
        drill_state([], ["US", "Bonds/Credit"]),
    ]

    for drill in drills:
        assert set(drill_defaults(GROUPS, drill)) <= set(options)


def test_no_groups_yields_no_default():
    assert drill_defaults([], None) == ()


# Alignment with Intraday -------------------------------------------------------


def test_untouched_selection_is_aligned():
    result = _run(["US / Core"], defaults=("US / Core",))

    assert not _is_narrowed(result)
    assert _summary(result) == "1 group · 2 securities"


def test_pick_order_does_not_count_as_a_change():
    result = _run(["US / Cash", "US / Core"], defaults=("US / Core", "US / Cash"))

    assert not _is_narrowed(result)


def test_edited_selection_is_flagged_against_intraday():
    result = _run(["US / Sectors", "Canada / Sectors"], defaults=("US / Sectors",))

    assert _is_narrowed(result)
    assert _summary(result) == (
        "2 groups · 3 securities · differs from Intraday (US / Sectors)"
    )


def test_a_whole_region_default_is_named_as_the_region():
    defaults = drill_defaults(GROUPS, drill_state([], ["Canada"]))
    result = _run(["Canada / Core"], defaults=defaults)

    assert _summary(result) == "1 group · 1 securities · differs from Intraday (Canada)"


def test_a_single_group_region_default_keeps_the_group_name():
    result = _run(defaults=("Global / Commodity",))

    assert result.defaults_label == "Global / Commodity"


def test_emptied_selection_differs_from_a_default():
    assert _is_narrowed(_run(defaults=("US / Core",)))


def test_widget_key_changes_with_the_version():
    assert facet_key("market-etf") == "market-etf-facet-tiles-v0"
    assert facet_key("market-etf", 3) == "market-etf-facet-tiles-v3"
