from pathlib import Path
import tomllib

import streamlit as st

disclaimer_dir = Path(__file__).parent.parent


def _get_version() -> str:
    with open(disclaimer_dir.joinpath("pyproject.toml"), "rb") as f:
        return tomllib.load(f)["project"]["version"]


st.title("ℹ️ About Portfolio Tuner")

if disclaimer_dir.exists():
    st.markdown(disclaimer_dir.joinpath("LEGAL.md").read_text(encoding="utf-8"))

else:
    st.error("LEGAL.md not found. Please ensure it exists at the repository root.")

st.subheader("Version")
try:
    st.write(_get_version())
except Exception:
    st.error(
        "Failed to get version. Please ensure pyproject.toml exists at the repository root."
    )
