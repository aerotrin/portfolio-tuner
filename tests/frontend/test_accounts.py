from types import SimpleNamespace

from frontend.shared.accounts import (
    account_label,
    account_labels,
    market_priced_symbols,
)


def _acc(id_: str, type_: str, number: str) -> SimpleNamespace:
    return SimpleNamespace(id=id_, type=type_, number=number)


def test_account_label_visible():
    assert account_label("TFSA", "12345", hide=False) == "TFSA #12345"


def test_account_label_hidden_keeps_last_two():
    assert account_label("TFSA", "12345", hide=True) == "TFSA ••45"


def test_account_label_hidden_masks_short_number_entirely():
    assert account_label("TFSA", "45", hide=True) == "TFSA ••"


def test_account_labels_visible():
    accounts = [_acc("a", "TFSA", "12345"), _acc("b", "RRSP", "67890")]
    assert account_labels(accounts, hide=False) == {
        "a": "TFSA #12345",
        "b": "RRSP #67890",
    }


def test_account_labels_hidden_same_tail_different_type_stay_short():
    accounts = [_acc("a", "TFSA", "12345"), _acc("b", "RRSP", "99945")]
    assert account_labels(accounts, hide=True) == {"a": "TFSA ••45", "b": "RRSP ••45"}


def test_account_labels_hidden_collision_shows_more_digits():
    accounts = [
        _acc("a", "TFSA", "12345"),
        _acc("b", "TFSA", "98745"),
        _acc("c", "RRSP", "55511"),
    ]
    assert account_labels(accounts, hide=True) == {
        "a": "TFSA ••345",
        "b": "TFSA ••745",
        "c": "RRSP ••11",
    }


def test_account_labels_hidden_never_reveals_full_number():
    accounts = [_acc("a", "TFSA", "1145"), _acc("b", "TFSA", "2145")]
    labels = account_labels(accounts, hide=True)
    assert len(set(labels.values())) == 2
    assert all("1145" not in v and "2145" not in v for v in labels.values())


def test_account_labels_hidden_short_numbers_fall_back_to_counter():
    accounts = [_acc("a", "TFSA", "45"), _acc("b", "TFSA", "46")]
    assert account_labels(accounts, hide=True) == {
        "a": "TFSA •• (1)",
        "b": "TFSA •• (2)",
    }


def test_market_priced_symbols_leave_out_fixed_income():
    open_positions = [
        {"symbol": "AAPL", "category": "Equity"},
        {"symbol": "AAPL", "category": "Call Option"},
        {"symbol": "GIC-5.00-20261107", "category": "Fixed Income"},
    ]

    assert market_priced_symbols(open_positions) == {"AAPL"}
    assert market_priced_symbols([]) == set()
