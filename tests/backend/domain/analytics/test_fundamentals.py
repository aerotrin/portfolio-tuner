from datetime import datetime

import pytest

from src.backend.domain.analytics.fundamentals import derive_fundamentals
from src.backend.domain.entities.security import Fundamentals, Profile


def _profile(**fields) -> Profile:
    return Profile(symbol="AAA", date=datetime(2024, 1, 1), **fields)


def test_stock_ratios_follow_the_price() -> None:
    profile = _profile(
        marketCap=1.0e9,
        epsTrailing=5.0,
        epsForward=8.0,
        dividendRate=2.0,
        sharesOutstanding=1.0e7,
    )

    result = derive_fundamentals(profile, 100.0)

    assert result.market_cap == pytest.approx(1.0e9)
    assert result.trailing_pe == pytest.approx(20.0)
    assert result.forward_pe == pytest.approx(12.5)
    assert result.eps == 5.0
    assert result.dividend_yield == pytest.approx(0.02)
    assert result.net_assets is None

    doubled = derive_fundamentals(profile, 200.0)

    assert doubled.market_cap == pytest.approx(2.0e9)
    assert doubled.trailing_pe == pytest.approx(40.0)
    assert doubled.dividend_yield == pytest.approx(0.01)


def test_fund_shows_net_assets_and_no_market_cap() -> None:
    profile = _profile(epsTrailing=2.5, dividendRate=1.0, netAssets=2.0e10)

    result = derive_fundamentals(profile, 50.0)

    assert result.market_cap is None
    assert result.net_assets == 2.0e10
    assert result.trailing_pe == pytest.approx(20.0)
    assert result.forward_pe is None
    assert result.dividend_yield == pytest.approx(0.02)


def test_loss_making_company_has_eps_but_no_pe() -> None:
    result = derive_fundamentals(_profile(epsTrailing=-1.5, epsForward=0.0), 30.0)

    assert result.eps == -1.5
    assert result.trailing_pe is None
    assert result.forward_pe is None


def test_market_cap_falls_back_to_the_stored_value_without_a_share_count() -> None:
    result = derive_fundamentals(_profile(marketCap=3.0e9), 10.0)

    assert result.market_cap == 3.0e9


@pytest.mark.parametrize("price", [None, 0.0, float("nan")])
def test_without_a_price_only_stored_figures_remain(price) -> None:
    profile = _profile(
        marketCap=3.0e9, epsTrailing=5.0, dividendRate=2.0, sharesOutstanding=1.0e7
    )

    result = derive_fundamentals(profile, price)

    assert result.model_dump() == Fundamentals(market_cap=3.0e9, eps=5.0).model_dump()


def test_missing_profile_gives_nothing() -> None:
    assert derive_fundamentals(None, 100.0).model_dump() == Fundamentals().model_dump()


def test_non_finite_inputs_are_ignored() -> None:
    profile = _profile(epsTrailing=float("nan"), dividendRate=float("inf"))

    assert (
        derive_fundamentals(profile, 100.0).model_dump() == Fundamentals().model_dump()
    )
