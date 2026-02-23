from typing import Any

import pandas as pd


def make_scalar_wide_df(data: dict[str, Any]) -> pd.DataFrame:
    if all(isinstance(v, dict) for v in data.values()):
        df = pd.DataFrame.from_dict(data, orient="index")
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(
                df["timestamp"], errors="coerce", format="ISO8601"
            )
        return df

    # single record
    else:
        df = pd.DataFrame.from_records([data])
        if "symbol" not in df.columns:
            raise ValueError("Single-record dict must contain a 'symbol' key.")
        return df


def make_timeseries_wide_df(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """
    Make a wide dataframe from a dataframe of timeseries data for a given metric.
    The dataframe is pivoted on the date column, and the values are the timeseries data.
    """
    df = df.copy()
    df = df.pivot(index="date", columns="symbol", values=metric)
    df = df.sort_index().ffill()

    return df


def make_timeseries_long_df(data: dict[str, list]) -> pd.DataFrame:
    """
    Make a long dataframe from a dictionary of timeseries data.
    """
    records = []
    for _, values in data.items():
        for value in values:
            records.append(value)
    df = pd.DataFrame(records)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    else:
        raise ValueError("date column not found in data")
    return df


def add_sparkline(
    base_data: pd.DataFrame,
    close_eod: pd.DataFrame,
    add_intraday_close: bool = False,
) -> pd.DataFrame:
    """
    Fast sparkline generator with vectorized operations.
    """
    base_data = base_data.copy()
    close_eod = close_eod.sort_index().ffill()

    # Pre-convert entire DataFrame → dict of {symbol: list_of_closes}
    series_dict = {
        symbol: col.dropna().tolist()
        for symbol, col in close_eod.items()
        if symbol in base_data.index
    }

    # Assign directly
    base_data["sparkline"] = base_data.index.map(series_dict.get)

    if add_intraday_close and "close" in base_data.columns:
        # Convert to lists with appended intraday close
        base_data["sparkline"] = [
            series + [close]
            for series, close in zip(base_data["sparkline"], base_data["close"])
        ]

    return base_data


def add_last_indicators(df: pd.DataFrame, indicators: pd.DataFrame) -> pd.DataFrame:
    """
    Add last calculated indicators to a dataframe.
    """
    df = df.copy()

    last_indicators = (
        indicators.sort_values("date").groupby("symbol", as_index=False).tail(1)
    ).copy()

    last_indicators = last_indicators.set_index("symbol", drop=True)

    df = df.merge(
        last_indicators.drop(columns=["date"]),
        left_index=True,
        right_index=True,
        how="left",
    )

    return df


def combine_header_data(
    header_symbols: list[str],
    securities: "SecurityData",
) -> pd.DataFrame:
    """
    Make a header dataframe from the combined security data.
    """
    header = make_scalar_wide_df({s: securities.quote[s] for s in header_symbols})

    header_bars = make_timeseries_long_df(
        {s: securities.bars[s] for s in header_symbols}
    )
    header_closes = make_timeseries_wide_df(header_bars, "close")
    header = add_sparkline(header, header_closes, add_intraday_close=True)

    return header
