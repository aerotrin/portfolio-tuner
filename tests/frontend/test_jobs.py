from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests
import streamlit as st

from frontend.shared import jobs


class _Rerun(Exception):
    pass


def _http_error(status_code: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(f"{status_code} error", response=response)


@pytest.fixture
def api(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(jobs, "get_api_client", lambda: client)
    monkeypatch.setattr(jobs.st, "rerun", MagicMock(side_effect=_Rerun))
    st.session_state.clear()
    st.session_state["job_id"] = "job-1"
    st.session_state["job_blocking"] = True
    st.session_state["job_status"] = "pending"
    st.session_state["_last_missing_attempted"] = {"AAPL"}
    yield client
    st.session_state.clear()


def test_missing_job_clears_state_and_reruns(api):
    api.get_refresh_job.side_effect = _http_error(404)

    with pytest.raises(_Rerun):
        jobs.check_job_status()

    assert "job_id" not in st.session_state
    assert "job_blocking" not in st.session_state
    assert "job_status" not in st.session_state
    assert "_last_missing_attempted" not in st.session_state
    assert st.session_state["job_just_lost"] is True


def test_other_http_errors_propagate(api):
    api.get_refresh_job.side_effect = _http_error(500)

    with pytest.raises(requests.HTTPError):
        jobs.check_job_status()

    assert st.session_state["job_id"] == "job-1"
    assert "job_just_lost" not in st.session_state


@pytest.mark.parametrize("exc", [requests.ConnectionError, requests.Timeout])
def test_unreachable_backend_keeps_polling(api, exc):
    api.get_refresh_job.side_effect = exc("backend down")

    jobs.check_job_status()

    assert st.session_state["job_id"] == "job-1"
    assert st.session_state["_last_missing_attempted"] == {"AAPL"}
    jobs.st.rerun.assert_not_called()


def _succeed(api):
    api.get_refresh_job.return_value = {
        "status": "success",
        "finished_at": "2026-11-23T10:00:00",
    }
    with pytest.raises(_Rerun):
        jobs.check_job_status()


def test_success_stamps_all_refreshed_pages(api):
    st.session_state["job_page"] = "portfolio"
    st.session_state["job_refreshed_pages"] = jobs.ALL_DATA_PAGES

    _succeed(api)

    assert st.session_state["last_refresh_by_page"] == {
        page: "2026-11-23T10:00:00" for page in jobs.ALL_DATA_PAGES
    }
    assert "job_refreshed_pages" not in st.session_state
    assert "job_id" not in st.session_state


def test_success_defaults_to_job_page(api):
    st.session_state["job_page"] = "market_etf"

    _succeed(api)

    assert st.session_state["last_refresh_by_page"] == {
        "market_etf": "2026-11-23T10:00:00"
    }


def test_success_remembers_symbols_that_failed(api):
    api.get_refresh_job.return_value = {
        "status": "success",
        "finished_at": "2026-11-23T10:00:00",
        "failed_symbols": ["SPY", "QQQ"],
    }

    with pytest.raises(_Rerun):
        jobs.check_job_status()

    assert st.session_state["last_job_failed_symbols"] == ["SPY", "QQQ"]


def test_failed_symbols_message_names_a_single_symbol():
    assert jobs.failed_symbols_message(["SPY"]) == (
        "Refresh finished, but 1 symbol could not be updated: SPY. "
        "Refresh again to retry."
    )


def test_failed_symbols_message_truncates_a_long_list():
    message = jobs.failed_symbols_message(["A", "B", "C", "D", "E", "F", "G"])

    assert "7 symbols could not be updated: A, B, C, D, E and 2 more." in message


# ── Refresh control fragment ────────────────────────────────────────────────


@pytest.fixture
def control(monkeypatch):
    """Idle session with the Streamlit calls of the refresh control stubbed."""
    client = MagicMock()
    client.refresh_securities.return_value = {"status": "accepted", "job_id": "job-9"}
    ui = MagicMock()
    ui.button.return_value = False
    monkeypatch.setattr(jobs, "get_api_client", lambda: client)
    monkeypatch.setattr(jobs.st, "button", ui.button)
    monkeypatch.setattr(jobs.st, "progress", ui.progress)
    monkeypatch.setattr(jobs.st, "toast", ui.toast)
    monkeypatch.setattr(jobs.st, "rerun", MagicMock(side_effect=_Rerun))
    monkeypatch.setattr(jobs.time, "sleep", ui.sleep)
    monkeypatch.setattr(jobs, "_rerun_fragment", MagicMock(side_effect=_Rerun))
    monkeypatch.setattr(jobs, "check_job_status", ui.check_job_status)
    st.session_state.clear()
    jobs.set_page_symbols("market_etf", ["SPY", "QQQ"])
    yield SimpleNamespace(api=client, ui=ui)
    st.session_state.clear()


def test_start_refresh_job_reruns_the_page_by_default(control):
    with pytest.raises(_Rerun):
        jobs.start_refresh_job(["SPY"], blocking=False, active_page="market_etf")

    assert st.session_state["job_id"] == "job-9"


def test_start_refresh_job_can_leave_the_page_alone(control):
    jobs.start_refresh_job(
        ["SPY"], blocking=False, active_page="market_etf", rerun=False
    )

    assert st.session_state["job_id"] == "job-9"
    jobs.st.rerun.assert_not_called()


def test_page_symbols_are_ignored_on_another_page(control):
    assert jobs._page_symbols("market_etf") == ["SPY", "QQQ"]
    assert jobs._page_symbols("portfolio") == []


def test_click_starts_a_job_for_the_page_and_reruns_only_the_fragment(control):
    control.ui.button.return_value = True

    with pytest.raises(_Rerun):
        jobs._refresh_control("market_etf", polled_by_timer=False)

    control.api.refresh_securities.assert_called_once()
    assert control.api.refresh_securities.call_args[0][0] == ["SPY", "QQQ"]
    assert st.session_state["job_blocking"] is False
    jobs.st.rerun.assert_not_called()


def test_idle_control_without_a_click_does_nothing(control):
    jobs._refresh_control("market_etf", polled_by_timer=False)

    control.api.refresh_securities.assert_not_called()
    control.ui.progress.assert_not_called()


def test_click_before_the_page_registered_its_symbols_starts_nothing(control):
    control.ui.button.return_value = True

    jobs._refresh_control("portfolio", polled_by_timer=False)

    control.api.refresh_securities.assert_not_called()


def test_auto_refresh_starts_a_job_when_due(control):
    st.session_state[jobs.AUTO_REFRESH_ON] = True

    with pytest.raises(_Rerun):
        jobs._refresh_control("market_etf", polled_by_timer=False)

    control.api.refresh_securities.assert_called_once()


def test_running_job_shows_progress_and_polls_itself(control):
    st.session_state.update(job_id="job-1", job_blocking=False, job_progress=40)

    with pytest.raises(_Rerun):
        jobs._refresh_control("market_etf", polled_by_timer=False)

    control.ui.check_job_status.assert_called_once()
    assert control.ui.progress.call_args[0][0] == 40
    control.ui.sleep.assert_called_once_with(jobs.REFRESH_POLL_SEC)
    control.ui.button.assert_not_called()


def test_running_job_on_a_timer_does_not_sleep_or_rerun(control):
    st.session_state.update(job_id="job-1", job_blocking=False)

    jobs._refresh_control("market_etf", polled_by_timer=True)

    control.ui.check_job_status.assert_called_once()
    assert control.ui.progress.call_args[0][0] == 0
    control.ui.sleep.assert_not_called()
    jobs._rerun_fragment.assert_not_called()


def test_blocking_job_disables_the_button_and_is_not_polled_here(control):
    st.session_state.update(job_id="job-1", job_blocking=True)

    jobs._refresh_control("market_etf", polled_by_timer=False)

    assert control.ui.button.call_args.kwargs["disabled"] is True
    control.ui.check_job_status.assert_not_called()
    control.ui.progress.assert_not_called()


# ── Auto refresh timing ─────────────────────────────────────────────────────


@pytest.fixture
def clock(monkeypatch):
    now = SimpleNamespace(value=1000.0)
    monkeypatch.setattr(jobs.time, "monotonic", lambda: now.value)
    st.session_state.clear()
    yield now
    st.session_state.clear()


def test_auto_refresh_is_never_due_with_the_toggle_off(clock):
    assert jobs.auto_refresh_due("market_etf") is False


def test_page_never_refreshed_this_session_is_due_at_once_then_waits(clock):
    st.session_state[jobs.AUTO_REFRESH_ON] = True
    interval_sec = jobs.config.auto_refresh_data_interval / 1000

    assert jobs.auto_refresh_due("market_etf") is True
    assert jobs.auto_refresh_due("market_etf") is False

    clock.value += interval_sec + 1
    assert jobs.auto_refresh_due("market_etf") is True


def test_page_already_refreshed_arms_its_timer_first(clock):
    st.session_state[jobs.AUTO_REFRESH_ON] = True
    st.session_state["last_refresh_by_page"] = {"portfolio": "2026-11-26T10:00:00"}
    interval_sec = jobs.config.auto_refresh_data_interval / 1000

    assert jobs.auto_refresh_due("portfolio") is False
    clock.value += interval_sec + 1
    assert jobs.auto_refresh_due("portfolio") is True


def test_pages_keep_independent_timers(clock):
    st.session_state[jobs.AUTO_REFRESH_ON] = True

    assert jobs.auto_refresh_due("market_etf") is True
    assert jobs.auto_refresh_due("market_stock") is True


# ── Fragment rerun fallback ─────────────────────────────────────────────────


def test_fragment_rerun_falls_back_to_a_page_rerun(monkeypatch):
    calls = []

    def fake_rerun(scope="app"):
        calls.append(scope)
        if scope == "fragment":
            raise jobs.StreamlitAPIException("not in a fragment rerun")

    monkeypatch.setattr(jobs.st, "rerun", fake_rerun)

    jobs._rerun_fragment()

    assert calls == ["fragment", "app"]
