from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib

import streamlit as st


def get_frontend_version() -> str:
    # Preferred: installed package metadata
    try:
        return version("portfolio-tuner-frontend")
    except PackageNotFoundError:
        pass

    # Fallback: read pyproject.toml
    candidates = [
        Path("pyproject.toml"),
        Path(__file__).resolve().parents[3] / "pyproject.toml",
    ]

    for p in candidates:
        if p.exists():
            with p.open("rb") as f:
                return tomllib.load(f)["project"]["version"]

    return "dev"


disclaimer_path = Path("LEGAL.md")

st.title("ℹ️ About Portfolio Tuner")

if disclaimer_path.exists():
    st.markdown(disclaimer_path.read_text(encoding="utf-8"))

else:
    st.error("LEGAL.md not found. Please ensure it exists at the repository root.")

st.subheader("Version")
st.write(get_frontend_version())
