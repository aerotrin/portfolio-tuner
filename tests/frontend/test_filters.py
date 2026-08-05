"""Tests for the pure cascade behind the Performance tab facet filter.

`_cascade` takes the raw selections as arguments rather than reading session
state, so these run without a Streamlit runtime.

Labels are deliberately non-unique here ("Core" under both US and Canada),
mirroring symbols.yml: a group is identified by region + type + label.
"""

from frontend.shared.symbols_loader import SymbolGroup
from frontend.widgets.filters import _cascade, facet_keys

US_CORE = SymbolGroup(label="Core", type="Equity", region="US", symbols=("SPY", "VTI"))
US_SECTORS = SymbolGroup(
    label="Sectors", type="Equity", region="US", symbols=("XLK", "XLF")
)
US_CASH = SymbolGroup(label="Cash", type="Fixed Income", region="US", symbols=("BIL",))
CA_CORE = SymbolGroup(label="Core", type="Equity", region="Canada", symbols=("XIC.TO",))
COMMODITY = SymbolGroup(
    label="Commodity", type="Commodity", region="Global", symbols=("GLD", "SPY")
)

GROUPS = [US_CORE, US_SECTORS, US_CASH, CA_CORE, COMMODITY]


def _run(regions=(), types=(), labels=(), **kwargs):
    kwargs.setdefault("key_prefix", "test")
    return _cascade(GROUPS, regions, types, labels, **kwargs)


# Group identity ----------------------------------------------------------------


def test_duplicate_labels_get_distinct_keys():
    assert US_CORE.key == "us-equity-core"
    assert CA_CORE.key == "canada-equity-core"
    assert US_CORE.key != CA_CORE.key


def test_options_are_distinct_labels():
    """A label names a concept; it appears once however many regions carry it."""
    assert _run().label_options == ("Core", "Sectors", "Cash", "Commodity")


# Empty means all ---------------------------------------------------------------


def test_no_selection_yields_every_group():
    result = _run()

    assert len(result.groups) == len(GROUPS)
    assert result.region_options == ("US", "Canada", "Global")
    assert result.type_options == ("Equity", "Fixed Income", "Commodity")


def test_symbols_are_sorted_and_deduped_across_groups():
    # SPY appears in both "Core" (US) and "Commodity".
    result = _run()

    assert result.symbols == ("BIL", "GLD", "SPY", "VTI", "XIC.TO", "XLF", "XLK")


# Narrowing ---------------------------------------------------------------------


def test_region_narrows_type_and_label_options():
    result = _run(regions=["Canada"])

    assert result.type_options == ("Equity",)
    assert result.label_options == ("Core",)
    assert result.symbols == ("XIC.TO",)


def test_type_narrows_label_options():
    result = _run(regions=["US"], types=["Fixed Income"])

    assert result.label_options == ("Cash",)
    assert result.symbols == ("BIL",)


def test_a_label_spans_every_region_that_carries_it():
    """Picking "Core" with no region means Core everywhere, not just the first."""
    result = _run(labels=["Core"])

    assert result.groups == (US_CORE, CA_CORE)
    assert result.symbols == ("SPY", "VTI", "XIC.TO")


def test_region_narrows_a_label_that_spans_regions():
    result = _run(regions=["Canada"], labels=["Core"])

    assert result.groups == (CA_CORE,)
    assert result.symbols == ("XIC.TO",)


def test_label_selection_wins_over_the_wider_facets():
    result = _run(regions=["US"], labels=["Sectors"])

    assert result.symbols == ("XLF", "XLK")


def test_multiple_regions_union():
    result = _run(regions=["US", "Canada"])

    assert "Commodity" not in result.label_options
    assert "XIC.TO" in result.symbols and "SPY" in result.symbols


# Symmetric options -------------------------------------------------------------


def test_a_type_selection_narrows_the_region_options():
    """Both are clearable, so narrowing between them is always reversible."""
    result = _run(types=["Fixed Income"])

    assert result.region_options == ("US",)


def test_a_region_selection_narrows_the_type_options():
    result = _run(regions=["Canada"])

    assert result.type_options == ("Equity",)


def test_a_group_selection_never_narrows_the_region_options():
    """The group level holds a value by default, so constraining region upwards
    would hide regions before the user has touched anything."""
    result = _run(labels=["Sectors"])  # Sectors is US-only in this fixture

    assert result.region_options == ("US", "Canada", "Global")
    assert result.symbols == ("XLF", "XLK")


def test_options_stay_full_when_nothing_is_selected():
    result = _run()

    assert result.region_options == ("US", "Canada", "Global")
    assert result.type_options == ("Equity", "Fixed Income", "Commodity")


# Cascade invalidation ----------------------------------------------------------


def test_type_orphaned_by_region_change_is_dropped():
    # "Fixed Income" exists only in the US; switching to Canada must not blank out.
    result = _run(regions=["Canada"], types=["Fixed Income"])

    assert result.sel_types == ()
    assert result.symbols == ("XIC.TO",)  # empty selection falls back to all


def test_label_orphaned_by_region_change_is_dropped():
    # "Sectors" exists only in the US in this fixture.
    result = _run(regions=["Canada"], labels=["Sectors"])

    assert result.sel_labels == ()
    assert result.symbols == ("XIC.TO",)


def test_a_label_surviving_the_region_change_is_kept():
    # "Core" exists in Canada too, so it must not be dropped.
    result = _run(regions=["Canada"], labels=["Core"])

    assert result.sel_labels == ("Core",)


def test_label_orphaned_by_type_change_is_dropped():
    result = _run(types=["Commodity"], labels=["Core"])

    assert result.sel_labels == ()
    assert result.symbols == ("GLD", "SPY")


def test_unknown_region_is_ignored():
    result = _run(regions=["Atlantis"])

    assert result.sel_regions == ()
    assert len(result.groups) == len(GROUPS)


def test_unknown_label_is_ignored():
    result = _run(labels=["Nonexistent"])

    assert result.sel_labels == ()
    assert len(result.groups) == len(GROUPS)


def test_selections_never_escape_their_options():
    result = _run(regions=["Canada"], types=["Fixed Income"], labels=["Commodity"])

    assert set(result.sel_regions) <= set(result.region_options)
    assert set(result.sel_types) <= set(result.type_options)
    assert set(result.sel_labels) <= set(result.label_options)


# Defaults ----------------------------------------------------------------------


def test_untouched_state_is_not_narrowed():
    """When the stored value is exactly the default, Clear has nothing to do."""
    result = _run(labels=["Core"], default_labels=("Core",))

    assert result.sel_labels == result.default_labels == ("Core",)


def test_emptied_selection_differs_from_a_nonempty_default():
    result = _run(default_labels=("Core",))

    assert result.sel_labels == ()
    assert result.default_labels == ("Core",)


def test_orphaned_default_is_dropped_too():
    result = _run(regions=["Canada"], default_labels=("Sectors",))

    assert result.default_labels == ()


# Stored-value coercion ---------------------------------------------------------


def test_bare_string_region_is_treated_as_one_value():
    # A bare string is a Sequence[str] that would otherwise be iterated
    # character by character and never match an option.
    result = _run(regions="Canada")

    assert result.sel_regions == ("Canada",)
    assert result.symbols == ("XIC.TO",)


def test_bare_string_label_is_treated_as_one_value():
    result = _run(labels="Commodity")

    assert result.sel_labels == ("Commodity",)


# Empty inputs ------------------------------------------------------------------


def test_no_groups_yields_empty_everything():
    result = _cascade([], [], [], [], key_prefix="test")

    assert result.groups == () and result.symbols == ()
    assert result.label_options == ()


# Renderability -----------------------------------------------------------------


def test_every_selection_carries_a_usable_key_prefix():
    """A resolved selection must always be renderable — widget keys are derived
    from key_prefix, so there is no half-valid state to trip over."""
    assert _run().key_prefix == "test"
    assert facet_keys(_run().key_prefix) == {
        "region": "test-facet-region",
        "type": "test-facet-type",
        "label": "test-facet-label",
    }
