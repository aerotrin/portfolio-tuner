# portfolio-tuner

Portfolio tuner: FastAPI backend plus Streamlit dashboard for portfolio analytics, market data, and holdings management.

Portfolio Tuner is a Python dashboard built with FastAPI and Streamlit, backed by SQLite and SQLAlchemy, with interactive Plotly charts, Docker deployment, and market data from FMP and EODHD.
Tech Stack:
- FastAPI + Uvicorn backend, Streamlit frontend
- SQLite + SQLAlchemy for persistence
- Plotly for interactive visualizations
- Pandas/NumPy for analytics with openpyxl for importing from Excel
- FMP & EODHD for market data
- Docker & Docker Compose for deployment
- uv for dependency management

## Structure

- **backend/** – FastAPI app (`src/`), empty `tests/`, `pyproject.toml`, `Dockerfile`
- **frontend/** – Streamlit app (`src/`), empty `tests/`, `pyproject.toml`, `Dockerfile`
- **config/** – Symbols YAML (copy `symbols.example.yml` to `symbols.yml`)
- **docs/** – High-level architecture (`architecture.mmd`)
- **examples/** – Sample data (e.g. `records.xlsx`)

One root `.env` for both services (copy from `.env.example` and fill in). Each app loads it and ignores vars it doesn’t use; see `.env.example` for variables and defaults.

## Run with Docker Compose (recommended)

1. From repo root: copy `.env.example` to `.env` and set `FMP_API_KEY`, `EODHD_API_KEY`, and any other values.
2. Copy `config/symbols.example.yml` → `config/symbols.yml`; edit as needed.
3. From repo root:
   ```bash
   docker compose up --build
   ```
4. Open streamlit at http://localhost:8501.

## Run with uv (local dev)

1. From repo root: copy `.env.example` to `.env` and populate. Ensure `config/symbols.yml` exists (copy from `config/symbols.example.yml`).
2. **FastAPI Backend**: from repo root
   ```bash
   cd backend
   uv run uvicorn api.app:app --reload
   ```
3. **Streamlit Frontend**: from repo root
   ```bash
   cd frontend
   uv run python -m streamlit run src/app.py
   ```
4. Open streamlit at http://localhost:8501.

