import logging
import time

import requests
import streamlit as st
from streamlit.errors import StreamlitAPIException
from streamlit_autorefresh import st_autorefresh

from frontend.services.streamlit_data import get_api_client
from frontend.shared.env_loader import config

logger = logging.getLogger(__name__)

ALL_DATA_PAGES = ["market_etf", "market_stock", "portfolio"]


FAILED_SYMBOLS_SHOWN = 5


def failed_symbols_message(failed: list[str]) -> str:
    """Toast text for a refresh that finished without some symbols."""
    shown = ", ".join(failed[:FAILED_SYMBOLS_SHOWN])
    more = len(failed) - FAILED_SYMBOLS_SHOWN
    names = f"{shown} and {more} more" if more > 0 else shown
    count = "1 symbol" if len(failed) == 1 else f"{len(failed)} symbols"
    return (
        f"Refresh finished, but {count} could not be updated: {names}. "
        "Refresh again to retry."
    )


def _clear_job_state() -> None:
    for k in [
        "job_id",
        "job_force",
        "job_blocking",
        "job_status",
        "job_page",
        "job_refreshed_pages",
        "job_started_at",
        "job_progress",
        "job_error",
    ]:
        st.session_state.pop(k, None)


def start_refresh_job(
    symbols: list[str],
    blocking: bool,
    force: bool = False,
    active_page: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    refreshed_pages: list[str] | None = None,
    rerun: bool = True,
) -> None:
    """Start a refresh job. ``refreshed_pages`` lists the pages whose data the
    job covers (stamped as refreshed on success); defaults to ``active_page``.
    Pass ``rerun=False`` from a fragment that shows the job's progress itself.
    """
    job_id = st.session_state.get("job_id")
    if job_id:
        st.toast(
            "Refresh job already in progress. Please wait for it to complete.",
            icon="⚠️",
        )
        st.stop()

    if symbols:
        api = get_api_client()
        resp = api.refresh_securities(
            symbols,
            force=force,
            start_date=start_date,
            end_date=end_date,
        )
        status = resp.get("status")
        job_type = "Forced" if force else "Smart"
        if status == "accepted":
            job_id = resp["job_id"]
            st.session_state["job_id"] = job_id
            st.session_state["job_force"] = force
            st.session_state["job_blocking"] = blocking
            st.session_state["job_status"] = "pending"
            st.session_state["job_page"] = active_page  # may be None
            st.session_state["job_refreshed_pages"] = refreshed_pages
            logger.info("%s refresh job accepted: %s", job_type, job_id)
            st.toast("Refresh started", icon="🔄")
            if rerun:
                st.rerun()
        elif status == "skipped":
            logger.info("%s refresh job skipped due to cooldown: %s", job_type, resp)
            st.toast("Refresh skipped", icon="❌")
        else:
            st.session_state["job_error"] = resp.get("error")
            logger.error("%s refresh job failed: %s", job_type, resp)
            st.toast("Refresh failed", icon="❌")
        return None
    else:
        logger.warning("No symbols to refresh")
        st.toast("No symbols to refresh", icon="❌")
        return None


def auto_refresh_if_missing(
    missing_symbols: list[str],
    active_page: str,
    start_date: str | None,
    end_date: str | None,
) -> None:
    """Trigger a blocking auto-refresh for missing symbols.

    If any missing symbol was already attempted in a previous job and is still
    unavailable, show an error for all missing symbols and stop rendering.
    Otherwise, attempt to fetch all missing symbols.

    Clear ``_last_missing_attempted`` (e.g. on Force Refresh) to allow retrying.
    """
    if not missing_symbols:
        return

    last_attempted: set[str] = st.session_state.get("_last_missing_attempted", set())

    # Any missing symbol that was already attempted → fetch failed; error and stop.
    if set(missing_symbols) & last_attempted:
        logger.warning(
            "Symbols still missing after refresh attempt, stopping render: %s",
            sorted(missing_symbols),
        )
        st.error(
            f"The following symbols could not be fetched"
            f": **{', '.join(sorted(missing_symbols))}**. Unable to proceed. "
            f"Use **Force Data Refresh** in the sidebar to retry.",
            icon="❌",
        )
        st.stop()

    st.session_state["_last_missing_attempted"] = set(missing_symbols)
    start_refresh_job(
        symbols=missing_symbols,
        blocking=True,
        active_page=active_page,
        start_date=start_date,
        end_date=end_date,
    )


AUTO_REFRESH_ON = "auto_refresh_on"


def _sync_auto_refresh_on() -> None:
    st.session_state[AUTO_REFRESH_ON] = st.session_state["auto_refresh_toggle"]


def render_auto_refresh_toggle() -> None:
    """Toggle for periodic background data refresh, shown next to Refresh Data.

    Each page renders its own toggle (element ids include the page), and a
    widget's value is dropped on a page switch. The setting therefore lives in
    ``AUTO_REFRESH_ON``: it seeds every page's toggle and is updated by the
    change callback, which runs before the script, so it is current for all
    readers in a run.
    """
    minutes = max(1, round(config.auto_refresh_data_interval / 60_000))
    st.toggle(
        "Auto",
        value=st.session_state.get(AUTO_REFRESH_ON, False),
        key="auto_refresh_toggle",
        help=f"Automatically refresh market data every {minutes} min",
        on_change=_sync_auto_refresh_on,
    )


def set_page_symbols(active_page: str, symbols: list[str]) -> None:
    """Record the symbols a refresh of this page covers.

    The page is stored with them because the refresh control renders in the
    header, before a page has computed its symbols: without it, the first
    run after a page switch would see the previous page's list.
    """
    st.session_state["page_symbols"] = symbols
    st.session_state["page_symbols_page"] = active_page


def _page_symbols(active_page: str) -> list[str]:
    if st.session_state.get("page_symbols_page") != active_page:
        return []
    return st.session_state.get("page_symbols") or []


def auto_refresh_due(page: str) -> bool:
    """Whether the Auto toggle should start a refresh of this page now, with
    an independent cadence per page scope.

    Each page keeps its own timer in ``_last_auto_refresh_at_by_page`` so heavy
    market pages and the portfolio scope never postpone each other. A page that
    was never refreshed this session is due at once; one already refreshed
    (manual or blocking job) just arms its timer and is due an interval later.
    The timestamp is set when this returns True, so a skipped or failed
    attempt waits a full interval before retrying.
    """
    if not st.session_state.get(AUTO_REFRESH_ON):
        return False
    last_by_page: dict = st.session_state.setdefault(
        "_last_auto_refresh_at_by_page", {}
    )
    last = last_by_page.get(page)
    now = time.monotonic()

    if last is None:
        if page in st.session_state.get("last_refresh_by_page", {}):
            last_by_page[page] = now
            return False
    elif (now - last) * 1000 < config.auto_refresh_data_interval:
        return False

    last_by_page[page] = now
    return True


def check_job_status() -> None:
    job_id = st.session_state.get("job_id")
    if not job_id:
        return

    api = get_api_client()
    try:
        job = api.get_refresh_job(job_id)
    except (requests.ConnectionError, requests.Timeout):
        logger.debug("Backend unreachable while polling job %s", job_id)
        return
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 404:
            raise
        # The job registry is in-memory, so a backend restart loses the job.
        logger.warning("Refresh job %s no longer exists on the backend", job_id)
        _clear_job_state()
        st.session_state.pop("_last_missing_attempted", None)
        st.session_state["job_just_lost"] = True
        st.rerun()

    status = job.get("status") or "pending"
    st.session_state["job_status"] = status
    st.session_state["job_started_at"] = job.get("started_at")
    st.session_state["job_progress"] = job.get("progress_percent")
    logger.debug("Job status: %s, progress: %s", status, job.get("progress_percent"))

    if status == "success":
        logger.info("Securities refresh job %s succeeded", job_id)

        st.session_state["last_job_completed_at"] = job.get("finished_at")
        st.session_state["last_job_id"] = job_id
        st.session_state["last_job_type"] = (
            "forced" if st.session_state.get("job_force") else "smart"
        )
        st.session_state["job_just_completed"] = True
        st.session_state["last_job_failed_symbols"] = job.get("failed_symbols") or []

        page = st.session_state.get("job_page")
        pages = st.session_state.get("job_refreshed_pages") or ([page] if page else [])
        for refreshed_page in pages:
            st.session_state.setdefault("last_refresh_by_page", {})[refreshed_page] = (
                job.get("finished_at")
            )

        _clear_job_state()
        st.cache_data.clear()
        st.rerun()

    elif status == "error":
        logger.error("Refresh job failed for job %s", job_id)

        st.session_state["last_job_error"] = job.get("error")
        st.session_state["job_just_failed"] = True

        _clear_job_state()
        st.rerun()


REFRESH_POLL_SEC = 1
AUTO_REFRESH_TICK_SEC = 10
REFRESH_PROGRESS_WIDTH = 170


def _rerun_fragment() -> None:
    """Rerun only the calling fragment; a fragment-scoped rerun is not allowed
    while the fragment runs as part of a full page run, so fall back to that."""
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


def _refresh_control(active_page: str, polled_by_timer: bool) -> None:
    """Refresh Data button, or the running job's progress in its place.

    Runs as a fragment, so starting a refresh and following its progress
    rerun only this control. The page reruns once, when the job finishes and
    there is new data to load (check_job_status).
    """
    if st.session_state.get("job_id"):
        if st.session_state.get("job_blocking"):
            st.button(
                "Refresh Data",
                icon=":material/refresh:",
                disabled=True,
                key=f"{active_page}_refresh_button_disabled",
            )
            return
        check_job_status()
        p = st.session_state.get("job_progress")
        st.progress(
            0 if p is None else int(p),
            text="Refreshing data…",
            width=REFRESH_PROGRESS_WIDTH,
        )
        if not polled_by_timer:
            time.sleep(REFRESH_POLL_SEC)
            _rerun_fragment()
        return

    clicked = st.button(
        "Refresh Data",
        icon=":material/refresh:",
        type="secondary",
        key=f"{active_page}_refresh_button",
    )
    symbols = _page_symbols(active_page)
    if not symbols:
        return
    if clicked or auto_refresh_due(active_page):
        start_refresh_job(
            symbols=symbols,
            blocking=False,
            active_page=active_page,
            start_date=st.session_state.get("start_date"),
            end_date=st.session_state.get("end_date"),
            rerun=False,
        )
        if st.session_state.get("job_id"):
            _rerun_fragment()


def render_refresh_control(active_page: str) -> None:
    """Refresh Data button for a page header, with in-place progress.

    The fragment's timer is chosen on each full run: fast while a background
    job is running, a slow tick while Auto refresh is on (to notice when a
    refresh is due), and none otherwise.
    """
    running = bool(st.session_state.get("job_id")) and not st.session_state.get(
        "job_blocking"
    )
    auto = (
        st.session_state.get(AUTO_REFRESH_ON) and config.auto_refresh_data_interval > 0
    )
    if running:
        run_every: int | None = REFRESH_POLL_SEC
    elif auto:
        run_every = AUTO_REFRESH_TICK_SEC
    else:
        run_every = None
    # A fragment's wrapper block stretches; content width keeps the header tight
    with st.container(width="content"):
        st.fragment(_refresh_control, run_every=run_every)(active_page, running)


def render_refresh_job_ui(active_page: str) -> None:
    """
    Completion toasts, and the blocking banner: if job_blocking AND
    job_page == active_page, block rendering (st.stop), poll fast (500ms) and
    show the progress bar in the main area. Background jobs show their
    progress in the page header instead (render_refresh_control).
    """
    if st.session_state.pop("job_just_completed", False):
        failed = st.session_state.pop("last_job_failed_symbols", [])
        if failed:
            st.toast(failed_symbols_message(failed), icon="⚠️", duration="long")
        else:
            st.toast("Refresh complete", icon="✅")

    if st.session_state.pop("job_just_failed", False):
        st.toast("Refresh job failed", icon="❌")

    if st.session_state.pop("job_just_lost", False):
        st.toast("Refresh interrupted — backend restarted. Please retry.", icon="⚠️")

    job_id = st.session_state.get("job_id")
    if not job_id:
        return

    job_page = st.session_state.get("job_page")
    blocking = bool(st.session_state.get("job_blocking"))
    status = st.session_state.get("job_status") or "pending"

    is_running = status not in ("success", "error")

    if not is_running:
        return

    if blocking and job_page == active_page:
        # ---- MAIN AREA blocking UI ----
        p = st.session_state.get("job_progress")
        p = 0 if p is None else int(p)
        st.progress(
            p, text="Data refresh in progress. Please do not refresh browser window..."
        )

        # fast refresh + stop page content rendering
        st_autorefresh(interval=500, key="job_autorefresh_blocking")
        st.stop()
