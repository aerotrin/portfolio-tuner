"""Group filter for the market Performance tab.

One multiselect whose options are the group tiles of the Intraday treemap,
named by region ("US / Sectors"). Picking several compares them side by side,
which the treemap itself cannot show. Regions are not options: a region next
to one of its own groups would be redundant, so a region is its groups.

Split into `resolve_group_facets` (pure read) and `render_group_facets` (draw)
because `render_performance_view` needs the resolved symbol set at the top of the
function while the widget itself belongs further down the layout.

The untouched-state selection follows the Intraday treemap: `sync_facets_to_drill`
records what the map is zoomed into and starts a fresh widget whenever that
changes, so the filter falls back to a default derived from it. Nothing writes
to the widget key.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import streamlit as st

from frontend.shared.symbols_loader import REGION_ORDER, SymbolGroup, facet_sort_key

TILE_SEP = " / "


@dataclass(frozen=True)
class FacetSelection:
    """Resolved filter state: what is selected, and what is selectable."""

    groups: tuple[SymbolGroup, ...]  # groups under the selected tiles
    symbols: tuple[str, ...]  # sorted, deduped union of their symbols
    options: tuple[str, ...]  # every tile, in treemap order
    selected: tuple[str, ...]  # validated — unknown tiles already dropped
    defaults: tuple[str, ...]  # the untouched-state selection
    defaults_label: str  # the same, named as the treemap would: "US"
    key_prefix: str


def facet_key(key_prefix: str, version: int = 0) -> str:
    return f"{key_prefix}-facet-tiles-v{version}"


def _version_key(key_prefix: str) -> str:
    return f"{key_prefix}-facet-version"


def _current_key(key_prefix: str) -> str:
    return facet_key(key_prefix, st.session_state.get(_version_key(key_prefix), 0))


def _drill_key(key_prefix: str) -> str:
    return f"{key_prefix}-facet-drill"


def _group_tile(group: SymbolGroup) -> str:
    return f"{group.region}{TILE_SEP}{group.label}"


def _as_list(value: object) -> list[str]:
    """Coerce a stored widget value to a list, so a bare string is one value
    rather than a sequence of characters."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)  # type: ignore[call-overload]


def tile_options(groups: Sequence[SymbolGroup]) -> dict[str, tuple[SymbolGroup, ...]]:
    """Each selectable tile and the groups under it, region by region and in
    config order within a region. Tiles are looked up here rather than parsed
    back out of their text, since a label may itself contain a slash.
    """
    by_region: dict[str, list[SymbolGroup]] = {}
    for group in groups:
        by_region.setdefault(group.region, []).append(group)

    options: dict[str, tuple[SymbolGroup, ...]] = {}
    for region in sorted(by_region, key=lambda v: facet_sort_key(v, REGION_ORDER)):
        members = by_region[region]
        # A label repeated under two types is one tile on the map, so one option.
        for tile in dict.fromkeys(_group_tile(g) for g in members):
            options[tile] = tuple(g for g in members if _group_tile(g) == tile)
    return options


def drill_state(sel_types: Sequence[str], drill_parts: Sequence[str]) -> dict:
    """What the Intraday treemap shows: its type slice and the region and group
    zoomed into. A symbol tile counts as its group."""
    return {
        "types": sorted(sel_types),
        "region": drill_parts[0] if drill_parts else None,
        "group": drill_parts[1] if len(drill_parts) > 1 else None,
    }


def drill_defaults(
    groups: Sequence[SymbolGroup], drill: Mapping | None
) -> tuple[str, ...]:
    """Untouched-state selection for a treemap drill state.

    The selection is what the map shows: the group zoomed into, or the groups
    of the region zoomed into, narrowed to its type slice. A map that is
    neither zoomed nor sliced selects only the first group, so the tab opens
    on a readable handful of symbols rather than the whole universe.
    """
    drill = drill or {}
    types = set(drill.get("types") or ())
    region, group = drill.get("region"), drill.get("group")
    typed = [g for g in groups if g.type in types]

    if group:
        return (f"{region}{TILE_SEP}{group}",)
    if region:
        shown = [g for g in typed if g.region == region] or [
            g for g in groups if g.region == region
        ]
    else:
        shown = typed or list(groups[:1])
    return tuple(dict.fromkeys(_group_tile(g) for g in shown))


def _tiles_label(
    options: Mapping[str, tuple[SymbolGroup, ...]], tiles: Sequence[str]
) -> str:
    """Name a set of tiles, as its region when it is exactly one region's groups."""
    by_region: dict[str, set[str]] = {}
    for tile, members in options.items():
        by_region.setdefault(members[0].region, set()).add(tile)
    if len(tiles) > 1:
        for region, region_tiles in by_region.items():
            if region_tiles == set(tiles):
                return region
    return ", ".join(tiles)


def _select(
    groups: Sequence[SymbolGroup],
    raw: object,
    defaults: Sequence[str] = (),
    *,
    key_prefix: str,
) -> FacetSelection:
    """Pure selection — no Streamlit calls, so it is testable without a runtime.
    An empty selection means every group."""
    options = tile_options(groups)
    selected = tuple(dict.fromkeys(v for v in _as_list(raw) if v in options))
    picked = {g.key for tile in selected for g in options[tile]}
    final = tuple(g for g in groups if not selected or g.key in picked)
    valid_defaults = tuple(v for v in defaults if v in options)
    return FacetSelection(
        groups=final,
        symbols=tuple(sorted({s for g in final for s in g.symbols})),
        options=tuple(options),
        selected=selected,
        defaults=valid_defaults,
        defaults_label=_tiles_label(options, valid_defaults),
        key_prefix=key_prefix,
    )


def resolve_group_facets(
    groups: Sequence[SymbolGroup], key_prefix: str
) -> FacetSelection:
    """Read the current selection. Safe to call before the widget renders."""
    state = st.session_state
    defaults = drill_defaults(groups, state.get(_drill_key(key_prefix)))
    return _select(
        groups,
        state.get(_current_key(key_prefix), defaults),
        defaults,
        key_prefix=key_prefix,
    )


def reset_group_facets(key_prefix: str) -> None:
    """Start a fresh widget so the filter falls back to its default.

    A new key rather than a cleared one: the widget is identified by its key,
    so the browser keeps showing its old value when only the stored selection
    is dropped and the default changes underneath it.
    """
    key = _version_key(key_prefix)
    st.session_state[key] = st.session_state.get(key, 0) + 1


def _is_narrowed(selection: FacetSelection) -> bool:
    """Whether the filter has been moved off what the Intraday treemap shows."""
    return set(selection.selected) != set(selection.defaults)


def _summary(selection: FacetSelection) -> str:
    n_groups = len(selection.groups)
    text = (
        f"{n_groups} group{'' if n_groups == 1 else 's'} · "
        f"{len(selection.symbols)} securities"
    )
    if _is_narrowed(selection):
        text += f" · differs from Intraday ({selection.defaults_label})"
    return text


def sync_facets_to_drill(
    key_prefix: str, sel_types: Sequence[str], drill_parts: Sequence[str]
) -> None:
    """Point the filter at what the Intraday treemap now shows. Only a change
    of view resets it, so manual filter edits last until the next map click."""
    drill = drill_state(sel_types, drill_parts)
    key = _drill_key(key_prefix)
    if st.session_state.get(key) != drill:
        st.session_state[key] = drill
        reset_group_facets(key_prefix)


def render_group_facets(selection: FacetSelection, *, border: bool = True) -> None:
    """Draw the filter for a selection resolved in the same run."""
    with st.container(border=border):
        st.multiselect(
            ":material/filter_list: Compare groups",
            selection.options,
            default=list(selection.selected),
            placeholder="All groups",
            key=_current_key(selection.key_prefix),
        )

        foot = st.columns([6, 1], vertical_alignment="center")
        with foot[0]:
            st.caption(_summary(selection))
        with foot[1]:
            st.button(
                "Reset",
                type="tertiary",
                icon=":material/restart_alt:",
                help="Back to the Intraday treemap selection",
                disabled=not _is_narrowed(selection),
                on_click=reset_group_facets,
                args=(selection.key_prefix,),
                key=f"{selection.key_prefix}-facet-clear",
                width="stretch",
            )
