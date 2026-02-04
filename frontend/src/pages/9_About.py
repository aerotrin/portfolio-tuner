from pathlib import Path
import streamlit as st

disclaimer_path = Path("LEGAL.md")

st.title("ℹ️ About")

if disclaimer_path.exists():
    st.markdown(disclaimer_path.read_text(encoding="utf-8"))
else:
    st.error("LEGAL.md not found. Please ensure it exists at the repository root.")
