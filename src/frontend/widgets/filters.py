"""Cascading region/type/group filter for the market Performance tab.

Split into `resolve_group_facets` (pure read) and `render_group_facets` (draw)
because `render_performance_view` needs the resolved symbol set at the top of the
function while the widgets themselves belong further down the layout.

Cascade invalidation is intersect-on-read: at each level, stored values that are
no longer valid options are simply dropped. Nothing writes to session state, so
no callbacks or explicit reruns are needed — Streamlit independently prunes a
widget's stored value when it renders with narrowed options, and the two agree by
the next run.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import streamlit as st

from frontend.shared.symbols_loader import (
    REGION_ORDER,
    TYPE_ORDER,
    SymbolGroup,
    facet_sort_key,
)

REGION_LEVEL = "region"
TYPE_LEVEL = "type"
LABEL_LEVEL = "label"
LEVELS = (REGION_LEVEL, TYPE_LEVEL, LABEL_LEVEL)


@dataclass(frozen=True)
class FacetSelection:
    """Resolved filter state: what is selected, and what remains selectable."""

    groups: tuple[SymbolGroup, ...]  # groups surviving every level
    symbols: tuple[str, ...]  # sorted, deduped union of their symbols
    region_options: tuple[str, ...]  # narrowed by type
    type_options: tuple[str, ...]  # narrowed by region
    label_options: tuple[str, ...]  # distinct labels, narrowed by region + type
    sel_regions: tuple[str, ...]  # validated — orphans already dropped
    sel_types: tuple[str, ...]
    sel_labels: tuple[str, ...]
    default_labels: tuple[str, ...]  # the untouched-state selection
    key_prefix: str  # widget keys are derived, so any prefix stays renderable


def facet_keys(key_prefix: str) -> dict[str, str]:
    return {level: f"{key_prefix}-facet-{level}" for level in LEVELS}


def _as_list(value: object) -> list[str]:
    """Coerce a stored widget value to a list.

    Single-select widgets store a bare string or None, multi-select ones store a
    list. Without this, a stored string would be iterated character by character
    and never match an option.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)  # type: ignore[call-overload]


def _options(
    groups: Sequence[SymbolGroup], attr: str, order: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {getattr(g, attr) for g in groups}, key=lambda v: facet_sort_key(v, order)
        )
    )


def _matching(
    groups: Sequence[SymbolGroup],
    regions: Sequence[str],
    types: Sequence[str],
    labels: Sequence[str],
) -> list[SymbolGroup]:
    """Groups satisfying every non-empty selection. Empty means 'all'."""
    return [
        g
        for g in groups
        if (not regions or g.region in regions)
        and (not types or g.type in types)
        and (not labels or g.label in labels)
    ]


def _cascade(
    groups: Sequence[SymbolGroup],
    raw_regions: Sequence[str],
    raw_types: Sequence[str],
    raw_labels: Sequence[str],
    *,
    key_prefix: str,
    default_labels: Sequence[str] = (),
) -> FacetSelection:
    """Pure cascade — no Streamlit calls, so it is testable without a runtime."""
    raw_regions = _as_list(raw_regions)
    raw_types = _as_list(raw_types)
    raw_labels = _as_list(raw_labels)

    # Pass 1 — validate top-down, so orphan-dropping stays deterministic:
    # a region change may orphan a type, which in turn may orphan a label.
    hier_regions = _options(groups, "region", REGION_ORDER)
    sel_regions = tuple(v for v in raw_regions if v in hier_regions)
    after_region = _matching(groups, sel_regions, (), ())

    hier_types = _options(after_region, "type", TYPE_ORDER)
    sel_types = tuple(v for v in raw_types if v in hier_types)
    after_type = _matching(after_region, (), sel_types, ())

    # Selection is by label, not by group key: a label names a concept that can
    # span regions, so picking "Sectors" with no region selected means every
    # region's Sectors group. Region and type are what narrow it.
    hier_labels = tuple(dict.fromkeys(g.label for g in after_type))  # yaml order
    sel_labels = tuple(v for v in raw_labels if v in hier_labels)

    # Pass 2 — region and type narrow each other, so picking "Fixed Income"
    # leaves only the regions that have some. Both can be empty, which is what
    # makes mutual narrowing safe: either one can always be widened again.
    #
    # The group level deliberately does not narrow upwards. It holds a selection
    # by default, so letting it constrain region would hide every region without
    # a group of that name before the user has touched anything.
    region_options = _options(
        _matching(groups, (), sel_types, ()), "region", REGION_ORDER
    )
    sel_regions = tuple(v for v in sel_regions if v in region_options)

    type_options = _options(_matching(groups, sel_regions, (), ()), "type", TYPE_ORDER)
    sel_types = tuple(v for v in sel_types if v in type_options)

    label_options = tuple(
        dict.fromkeys(g.label for g in _matching(groups, sel_regions, sel_types, ()))
    )
    sel_labels = tuple(v for v in sel_labels if v in label_options)

    final = _matching(groups, sel_regions, sel_types, sel_labels)

    return FacetSelection(
        groups=tuple(final),
        symbols=tuple(sorted({s for g in final for s in g.symbols})),
        region_options=region_options,
        type_options=type_options,
        label_options=label_options,
        sel_regions=sel_regions,
        sel_types=sel_types,
        sel_labels=sel_labels,
        default_labels=tuple(v for v in default_labels if v in label_options),
        key_prefix=key_prefix,
    )


def resolve_group_facets(
    groups: Sequence[SymbolGroup],
    key_prefix: str,
    *,
    default_labels: Sequence[str] = (),
) -> FacetSelection:
    """Read the current selection. Safe to call before the widgets render."""
    keys = facet_keys(key_prefix)
    state = st.session_state
    return _cascade(
        groups,
        _as_list(state.get(keys[REGION_LEVEL])),
        _as_list(state.get(keys[TYPE_LEVEL])),
        _as_list(state.get(keys[LABEL_LEVEL], default_labels)),
        key_prefix=key_prefix,
        default_labels=default_labels,
    )


def _clear_facets(key_prefix: str) -> None:
    """Drop the stored selections so every level falls back to its default.

    Popping rather than assigning: writing a value to a widget key while also
    passing `default=` is what triggers Streamlit's "set via Session State"
    warning. Removing the key lets the widget re-initialise cleanly.
    """
    for key in facet_keys(key_prefix).values():
        st.session_state.pop(key, None)


def _is_narrowed(selection: FacetSelection) -> bool:
    """Whether Clear would change anything — i.e. we differ from the defaults."""
    return bool(
        selection.sel_regions
        or selection.sel_types
        or selection.sel_labels != selection.default_labels
    )


def render_group_facets(
    selection: FacetSelection,
    *,
    border: bool = True,
    show_summary: bool = True,
) -> None:
    """Draw the filter widgets for a selection resolved in the same run.

    If a `format_func` is ever added here, keep its output constant across runs:
    the button-group widgets serialize their state by formatted string, so an
    option label carrying a live count would make every stored selection look
    stale. Counts belong in the caption.
    """
    keys = facet_keys(selection.key_prefix)
    with st.container(border=border):
        if selection.region_options:
            st.pills(
                ":material/public: Region",
                selection.region_options,
                selection_mode="multi",
                default=list(selection.sel_regions),
                key=keys[REGION_LEVEL],
            )
        if selection.type_options:
            st.pills(
                ":material/category: Type",
                selection.type_options,
                selection_mode="multi",
                default=list(selection.sel_types),
                key=keys[TYPE_LEVEL],
            )

        st.multiselect(
            ":material/filter_list: Filter by groups",
            selection.label_options,
            default=list(selection.sel_labels),
            placeholder="All groups",
            key=keys[LABEL_LEVEL],
        )

        foot = st.columns([6, 1], vertical_alignment="center")
        with foot[0]:
            if show_summary:
                n_groups = len(selection.groups)
                st.caption(
                    f"{n_groups} group{'' if n_groups == 1 else 's'} · "
                    f"{len(selection.symbols)} securities"
                )
        with foot[1]:
            st.button(
                "Clear",
                type="tertiary",
                icon=":material/filter_list_off:",
                disabled=not _is_narrowed(selection),
                on_click=_clear_facets,
                args=(selection.key_prefix,),
                key=f"{selection.key_prefix}-facet-clear",
                width="stretch",
            )
