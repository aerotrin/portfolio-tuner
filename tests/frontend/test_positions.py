from frontend.shared.settings import LOSS_LIMIT, TAKE_PROFIT_LIMIT
from frontend.widgets.positions import holdings_shading_key
from frontend.widgets.treemaps import format_cap


def test_shading_key_states_the_take_profit_and_stop_loss_limits():
    key = holdings_shading_key()

    assert f"+{format_cap(TAKE_PROFIT_LIMIT)} or more" in key
    assert f"−{format_cap(abs(LOSS_LIMIT))} or worse" in key
