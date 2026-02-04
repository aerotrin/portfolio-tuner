# portfolio-tuner

Portfolio tuner: FastAPI backend plus Streamlit dashboard for portfolio analytics, market data, and holdings management.

## Structure

- **backend/** – FastAPI app (`src/`), empty `tests/`, `pyproject.toml`, `Dockerfile`
- **frontend/** – Streamlit app (`src/`), empty `tests/`, `pyproject.toml`, `Dockerfile`
- **config/** – Accounts and symbols YAML (copy `*.example.yml` to `accounts.yml` / `symbols.yml`)
- **docs/** – High-level architecture (`architecture.mmd`)
- **examples/** – Sample data (e.g. `records.xlsx`)

One root `.env` for both services (copy from `.env.example` and fill in). Each app loads it and ignores vars it doesn’t use; see `.env.example` for variables and defaults.

## Run with Docker Compose (recommended)

1. From repo root: copy `.env.example` to `.env` and set `FMP_API_KEY`, `EODHD_API_KEY`, and any other values.
2. Copy `config/accounts.example.yml` → `config/accounts.yml` and `config/symbols.example.yml` → `config/symbols.yml`; edit as needed.
3. From repo root:
   ```bash
   docker compose up --build
   ```
4. Open streamlit at http://localhost:8501.

## Run with uv (local dev)

1. From repo root: copy `.env.example` to `.env` and populate. Ensure `config/accounts.yml` and `config/symbols.yml` exist (copy from `config/*.example.yml`).
2. **FastAPI Backend**: from repo root
   ```bash
   cd backend
   uv run uvicorn src.app:app --reload
   ```
3. **Streamlit Frontend**: from repo root
   ```bash
   cd frontend
   uv run python -m streamlit run src/app.py
   ```
4. Open streamlit at http://localhost:8501.

