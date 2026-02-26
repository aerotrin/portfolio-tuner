import logging

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from frontend.services.streamlit_data import get_api_client

logger = logging.getLogger(__name__)


def _clear_job_state() -> None:
    for k in [
        "job_id",
        "job_force",
        "job_blocking",
        "job_status",
        "job_page",
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
) -> None:
    job_id = st.session_state.get("job_id")
    if job_id:
        st.toast(
            "Refresh job already in progress. Please wait for it to complete.", icon="⚠️"
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
            logger.info("%s refresh job accepted: %s", job_type, job_id)
            st.toast("Refresh started", icon="🔄")
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


def check_job_status() -> None:
    job_id = st.session_state.get("job_id")
    if not job_id:
        return

    api = get_api_client()
    job = api.get_refresh_job(job_id)

    status = job.get("status") or "pending"
    st.session_state["job_status"] = status
    st.session_state["job_started_at"] = job.get("started_at")
    st.session_state["job_progress"] = job.get("progress_percent")

    if status == "success":
        logger.info("Securities refresh job %s succeeded", job_id)

        st.session_state["last_job_completed_at"] = job.get("finished_at")
        st.session_state["last_job_id"] = job_id
        st.session_state["last_job_type"] = (
            "forced" if st.session_state.get("job_force") else "smart"
        )
        st.session_state["job_just_completed"] = True

        _clear_job_state()
        st.cache_data.clear()
        st.rerun()

    elif status == "error":
        logger.error("Refresh job failed for job %s", job_id)

        st.session_state["last_job_error"] = job.get("error")
        st.session_state["job_just_failed"] = True

        _clear_job_state()
        st.rerun()


def render_refresh_job_ui(active_page: str) -> None:
    """
    Rules:
    - If job_blocking AND job_page == active_page:
        * block rendering (st.stop)
        * fast poll (1000ms)
        * show progress bar in MAIN area (not sidebar)
    - Else:
        * show ONLY a sidebar-bottom caption (no progress)
        * slow poll (e.g. 5s) to catch completion
    """
    if st.session_state.pop("job_just_completed", False):
        st.toast("Refresh complete", icon="✅")

    if st.session_state.pop("job_just_failed", False):
        st.toast("Refresh job failed", icon="❌")

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
        st_autorefresh(interval=1000, key="job_autorefresh_blocking")
        st.stop()

    # ---- SIDEBAR bottom caption only ----
    with st.sidebar:
        st.divider()
        st.subheader("Refresh Status")
        st.caption("Refresh in progress…")
    # app global refresh will detect completion automatically, so no need to poll here
