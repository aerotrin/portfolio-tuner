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
