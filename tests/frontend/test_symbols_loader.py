from pathlib import Path

import pytest

from frontend.shared.symbols_loader import (
    DEFAULT_REGION,
    DEFAULT_TYPE,
    REGION_ORDER,
    TYPE_ORDER,
    SymbolGroup,
    facet_sort_key,
    load_symbols_config,
    slugify,
)

_ROOT = Path(__file__).resolve().parents[2]

_MINIMAL = """
benchmarks:
  label: Benchmarks
  symbols: [^GSPC]
snapshot:
  label: Market Snapshot
  symbols: [^GSPC]
base_market_etfs:
  - label: Index
    symbols: [VOO]
base_market_stocks:
  - label: Magnificent 7
    symbols: [AAPL]
"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "symbols.yml"
    path.write_text(body, encoding="utf-8")
    return path


# Backward compatibility --------------------------------------------------------


def test_groups_without_facets_get_defaults(tmp_path):
    """symbols.example.yml and pre-existing user configs have no type/region."""
    config = load_symbols_config(_write(tmp_path, _MINIMAL))

    group = config.base_market_etfs[0]
    assert group.type == DEFAULT_TYPE
    assert group.region == DEFAULT_REGION
    assert config.benchmarks.type == DEFAULT_TYPE


def test_shipped_example_config_parses():
    """Guards against the tracked template drifting away from the schema."""
    config = load_symbols_config(_ROOT / "symbols.example.yml")

    assert config.base_market_etfs
    assert all(g.region and g.type for g in config.base_market_etfs)


# Facet normalisation -----------------------------------------------------------


def test_facets_are_stripped_and_collapsed(tmp_path):
    body = _MINIMAL.replace(
        "  - label: Index\n",
        '  - label: Index\n    type: "  Fixed   Income "\n    region: " US "\n',
    )
    group = load_symbols_config(_write(tmp_path, body)).base_market_etfs[0]

    assert group.type == "Fixed Income"
    assert group.region == "US"


def test_blank_facet_falls_back_to_default(tmp_path):
    body = _MINIMAL.replace("  - label: Index\n", '  - label: Index\n    type: "   "\n')

    assert (
        load_symbols_config(_write(tmp_path, body)).base_market_etfs[0].type
        == DEFAULT_TYPE
    )


def test_facet_case_is_preserved(tmp_path):
    body = _MINIMAL.replace("  - label: Index\n", "  - label: Index\n    type: REITs\n")

    assert (
        load_symbols_config(_write(tmp_path, body)).base_market_etfs[0].type == "REITs"
    )


def test_blank_label_raises(tmp_path):
    # A falsy label would be discarded by the single-select fallback, silently
    # switching the user to a different group.
    body = _MINIMAL.replace("  - label: Index\n", '  - label: "   "\n')

    with pytest.raises(ValueError, match="label must not be empty"):
        load_symbols_config(_write(tmp_path, body))


def test_label_whitespace_is_collapsed(tmp_path):
    body = _MINIMAL.replace("  - label: Index\n", '  - label: "  Style   & Factor "\n')

    group = load_symbols_config(_write(tmp_path, body)).base_market_etfs[0]
    assert group.label == "Style & Factor"


def test_non_string_facet_raises(tmp_path):
    # TypeError from a mode="before" validator propagates uncaught, matching the
    # long-standing behaviour of the `symbols` validator.
    body = _MINIMAL.replace("  - label: Index\n", "  - label: Index\n    region: 42\n")

    with pytest.raises(TypeError, match="'region' must be a string"):
        load_symbols_config(_write(tmp_path, body))


# Keys and uniqueness -----------------------------------------------------------


def test_key_combines_region_type_and_label():
    group = SymbolGroup(
        label="Style & Factor", type="Equity", region="US", symbols=("SPY",)
    )

    assert group.key == "us-equity-style-factor"
    assert slugify("  Fixed Income | Cash  ") == "fixed-income-cash"


def test_the_same_label_under_different_regions_is_allowed(tmp_path):
    """`label` is the leaf under region/type — "Core" exists once per region."""
    body = _MINIMAL.replace(
        "  - label: Index\n    symbols: [VOO]\n",
        "  - label: Core\n    type: Equity\n    region: US\n    symbols: [VOO]\n"
        "  - label: Core\n    type: Equity\n    region: Canada\n    symbols: [XIC.TO]\n"
        "  - label: Core\n    type: Equity\n    region: World\n    symbols: [VEA]\n",
    )

    etfs = load_symbols_config(_write(tmp_path, body)).base_market_etfs

    assert [g.label for g in etfs] == ["Core", "Core", "Core"]
    assert len({g.key for g in etfs}) == 3


def test_the_same_label_under_different_types_is_allowed(tmp_path):
    body = _MINIMAL.replace(
        "  - label: Index\n    symbols: [VOO]\n",
        "  - label: Core\n    type: Equity\n    region: US\n    symbols: [VOO]\n"
        "  - label: Core\n    type: Fixed Income\n    region: US\n    symbols: [BIL]\n",
    )

    etfs = load_symbols_config(_write(tmp_path, body)).base_market_etfs
    assert len({g.key for g in etfs}) == 2


def test_fully_duplicated_group_raises(tmp_path):
    body = _MINIMAL.replace(
        "  - label: Index\n    symbols: [VOO]\n",
        "  - label: Core\n    type: Equity\n    region: US\n    symbols: [VOO]\n"
        "  - label: Core\n    type: Equity\n    region: US\n    symbols: [QQQ]\n",
    )

    with pytest.raises(ValueError, match="duplicate group 'Core'"):
        load_symbols_config(_write(tmp_path, body))


def test_labels_colliding_only_on_slug_raise(tmp_path):
    body = _MINIMAL.replace(
        "  - label: Index\n    symbols: [VOO]\n",
        "  - label: Style & Factor\n    symbols: [VOO]\n"
        "  - label: 'Style / Factor'\n    symbols: [QQQ]\n",
    )

    with pytest.raises(ValueError, match="duplicate group"):
        load_symbols_config(_write(tmp_path, body))


@pytest.mark.skipif(
    not (_ROOT / "symbols.yml").exists(),
    reason="symbols.yml is user-local (untracked); absent on CI",
)
def test_real_config_loads():
    """The working symbols.yml is what the app boots on — it must stay loadable."""
    config = load_symbols_config(_ROOT / "symbols.yml")

    assert len({g.key for g in config.base_market_etfs}) == len(config.base_market_etfs)


def test_same_label_across_etfs_and_stocks_is_allowed(tmp_path):
    body = _MINIMAL.replace("  - label: Magnificent 7\n", "  - label: Index\n")

    config = load_symbols_config(_write(tmp_path, body))

    assert (
        config.base_market_etfs[0].label
        == config.base_market_stocks[0].label
        == "Index"
    )


# Ordering ----------------------------------------------------------------------


def test_known_facets_sort_before_unknown_ones():
    # Derived from REGION_ORDER so editing the taxonomy doesn't break this.
    values = ["Zebra", "Atlantis", *reversed(REGION_ORDER)]

    assert sorted(values, key=lambda v: facet_sort_key(v, REGION_ORDER)) == [
        *REGION_ORDER,
        "Atlantis",
        "Zebra",
    ]


def test_type_order_covers_the_default():
    assert DEFAULT_TYPE in TYPE_ORDER
    assert DEFAULT_REGION in REGION_ORDER


# Existing symbol handling is unchanged -----------------------------------------


def test_symbols_are_upper_cased_and_stripped(tmp_path):
    body = _MINIMAL.replace("symbols: [VOO]", 'symbols: [" voo ", "qqq"]')

    assert load_symbols_config(_write(tmp_path, body)).base_market_etfs[0].symbols == (
        "VOO",
        "QQQ",
    )


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_symbols_config(tmp_path / "nope.yml")
