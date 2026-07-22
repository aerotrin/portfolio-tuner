$env:PYTHONPATH = "$PSScriptRoot\src"
uv run uvicorn backend.app:app --reload --port 8000 @args
