import pandas as pd

from frontend.presentation.settings import MOVER_SHOW_COUNT
from frontend.shared.config_loader import SymbolGroup


def create_mover_groups(
    quotes: pd.DataFrame,
    base_groups: list[SymbolGroup],
) -> list[SymbolGroup]:
    """Create mover groups (most active, gainers, losers) for CAD and USD currencies."""
    mover_groups = []

    for currency in ["USD", "CAD"]:
        sub_quotes = quotes[quotes["currency"] == currency]
        country = "US" if currency == "USD" else "Canada"

        # Most active (by volume)
        most_active = (
            sub_quotes.sort_values(by="volume", ascending=False)
            .head(MOVER_SHOW_COUNT)
            .index.tolist()
        )
        if most_active:
            mover_groups.append(
                SymbolGroup(
                    label=f"Most Active {country}",
                    symbols=tuple(most_active),
                )
            )

        # Top gainers (by change_percent descending)
        gainers = (
            sub_quotes[sub_quotes["change_percent"] > 0]
            .sort_values(by="change_percent", ascending=False)
            .head(MOVER_SHOW_COUNT)
            .index.tolist()
        )
        if gainers:
            mover_groups.append(
                SymbolGroup(
                    label=f"Top Gainers {country}",
                    symbols=tuple(gainers),
                )
            )

        # Top losers (by change_percent ascending)
        losers = (
            sub_quotes[sub_quotes["change_percent"] < 0]
            .sort_values(by="change_percent", ascending=True)
            .head(MOVER_SHOW_COUNT)
            .index.tolist()
        )
        if losers:
            mover_groups.append(
                SymbolGroup(
                    label=f"Top Losers {country}",
                    symbols=tuple(losers),
                )
            )

    return mover_groups + base_groups
