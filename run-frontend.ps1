$env:PYTHONPATH = "$PSScriptRoot\src"
uv run streamlit run src/frontend/app.py --server.port 8501 @args
