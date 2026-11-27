import math
from typing import Optional

from backend.domain.entities.security import Fundamentals, Profile


def _positive(value: Optional[float]) -> Optional[float]:
    if value is None or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _finite(value: Optional[float]) -> Optional[float]:
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def derive_fundamentals(
    profile: Optional[Profile], price: Optional[float]
) -> Fundamentals:
    """Price-sensitive ratios from the profile's stored inputs and a price.

    The profile is refreshed weekly; dividing its EPS, dividend rate and
    share count by the current price keeps the ratios in step with the quote.
    """
    if profile is None:
        return Fundamentals()

    price = _positive(price)
    eps_trailing = _finite(profile.epsTrailing)
    shares = _positive(profile.sharesOutstanding)
    dividend_rate = _positive(profile.dividendRate)

    def pe(eps: Optional[float]) -> Optional[float]:
        eps = _positive(eps)
        return price / eps if price and eps else None

    market_cap = shares * price if shares and price else _positive(profile.marketCap)

    return Fundamentals(
        market_cap=market_cap,
        net_assets=_positive(profile.netAssets),
        trailing_pe=pe(profile.epsTrailing),
        forward_pe=pe(profile.epsForward),
        eps=eps_trailing,
        dividend_yield=dividend_rate / price if dividend_rate and price else None,
    )
