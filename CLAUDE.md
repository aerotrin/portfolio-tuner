# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Conventions

- Use comments sparingly — only where logic is not self-evident.
- After changing a feature, check whether [README.md](README.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [docs/USER_GUIDE.md](docs/USER_GUIDE.md) need updates.

## Commands

**Install dependencies** (uv workspace — installs all packages):
```bash
uv sync --all-groups
```

**Run backend** (PowerShell — sets `PYTHONPATH` and launches uvicorn; extra flags pass through):
```powershell
.\run-backend.ps1
```

**Run frontend** (PowerShell — sets `PYTHONPATH` and launches streamlit; extra flags pass through):
```powershell
.\run-frontend.ps1
```

Both `run-backend.ps1` and `run-frontend.ps1` run from the repo root. They exist because the workspace members have no `build-system`, so `uv sync` never installs `backend`/`frontend` into the venv — imports raise `ModuleNotFoundError` (`No module named 'backend'` / `'frontend'`) unless `src/` is on `PYTHONPATH` (mirrors `ENV PYTHONPATH=/usr/src` in `src/frontend/Dockerfile`). To run the commands manually instead, set it first, run from `src/`:
```powershell
$env:PYTHONPATH = (Get-Location).Path
uv run uvicorn backend.app:app --reload --port 8000
uv run streamlit run frontend/app.py --server.port 8501
```
```bash
export PYTHONPATH=.
```

**Run all tests**:
```bash
uv run pytest tests/
```

**Run a single test file**:
```bash
uv run pytest tests/backend/domain/aggregates/test_portfolio.py
```

**Run with Docker** (preferred for full-stack):
```bash
docker compose up --build
```

**Format / lint**:
```bash
black src/
ruff check src/
mypy src/
```

**CI**: Tests run automatically via `.github/workflows/tests.yml` on push to `main`, `feat/**`, `fix/**`, and all PRs.

## Architecture

This is a **Hexagonal Architecture (Ports & Adapters)** Python monorepo managed by `uv` workspace.

**Workspace layout**:
- `src/backend/` — FastAPI application
- `src/frontend/` — Streamlit dashboard
- `tests/` — pytest suite (backend-heavy; frontend minimal)
- `supabase/schema.sql` — database schema (run once in Supabase SQL Editor)

### Backend layers (`src/backend/`)

| Layer | Path | Role |
|---|---|---|
| Domain | `domain/` | Pure business logic — no I/O, no framework dependencies |
| Application | `application/` | Use cases; orchestrates domain + ports |
| Infrastructure | `infra/` | Concrete adapters, DB repos, API routes |
| Shared | `shared/` | Config (Pydantic BaseSettings), logging |

**Domain aggregates** (`domain/aggregates/`):
- `Account` — replays transactions to derive positions, cash, external flows
- `Portfolio` — wraps Account with market data; runs analytics pipeline
- `PortfolioSimulator` — Monte Carlo optimization (Dirichlet weight sampling)
- `Security` — single-security analytics (technicals, performance)

**Application use cases** (`application/use_cases/`):
- `AccountManager` — account/transaction CRUD, portfolio reconstruction, Excel import
- `MarketDataManager` — quotes/bars/profiles fetch, background refresh, smart sync
- `PortfolioManager` — composes AccountManager + MarketDataManager
- `SimulatorManager` — drives Monte Carlo runs

**Infrastructure adapters** (`infra/adapters/`):
- `YFinanceClient` — default market data provider (free)
- `FMPClient` — Financial Modeling Prep (enabled via `ENABLE_FMP_AS_PRIMARY=true`)
- `ExcelPandasClient` — broker Excel ledger importer
- `RateLimiter` — thread-safe sliding-window rate limiter with exponential backoff

**API routes** (`infra/api/v1/routers/`): `accounts`, `securities`, `admin`, `optimizer`

**Auth**: JWT verified in `infra/api/v1/dependencies/auth.py` using ES256/P-256 (no network call). Each DB session sets Postgres role to `authenticated` and injects `auth.uid()` for RLS enforcement.

### Frontend layers (`src/frontend/`)

- `app.py` — entry point: Supabase auth, sidebar, session state bootstrap
- `pages/` — Streamlit multi-page app (auto-discovered)
- `services/streamlit_data.py` — `@st.cache_data`-wrapped API loaders
- `widgets/` — UI rendering components (one per concept: kpis, positions, optimizer, etc.)
- `shared/` — config, dataframe helpers, symbol loading from `symbols.yml`

### Database

**Supabase PostgreSQL** with Row-Level Security (RLS).

User-scoped tables (RLS enforced): `accounts`, `transactions`
Shared/global tables (no RLS): `quotes`, `bars`, `bars_sync_state`, `profiles`, `global_rates`

### Key data flows

**Portfolio reconstruction**: `AccountManager.build_account()` replays all transactions → `PortfolioManager.build_portfolio_from_account()` fetches securities concurrently → computes valuations, weights, correlations, MWRR.

**Market data refresh**: Frontend posts to `/admin/refresh-securities` → backend returns job ID (202) → background task fetches/upserts data → frontend polls `/jobs/{job_id}`.

**Token handling**: Frontend calls `supabase.auth.get_session()` on every Streamlit rerun to pick up rotated tokens; all API calls include `Authorization: Bearer <JWT>`.

## Environment variables

Copy `.env.example` → `.env`. Key variables:

| Variable | Purpose |
|---|---|
| `POSTGRES_URL` | Supabase PostgreSQL connection string |
| `SUPABASE_URL` / `SUPABASE_KEY` | Supabase project (frontend auth) |
| `SUPABASE_JWT_PUBLIC_KEY` | JWK JSON for ES256 JWT validation (backend) |
| `ENABLE_FMP_AS_PRIMARY` | `true` to use FMP instead of yfinance |
| `FMP_API_KEY` | Required if FMP enabled |
| `BACKEND_URL` | Defaults to `http://127.0.0.1:8000`; Docker uses `http://backend:8000` |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` |

**First-time database setup**: Run `supabase/schema.sql` in Supabase SQL Editor, then create first user via Supabase Authentication → Users.

## Adding new functionality

**New market data provider**: Implement `application/ports/` interface → create adapter in `infra/adapters/` → register in `app.py` lifespan. No domain/application changes needed.

**New page**: Create `src/frontend/pages/N_PageName.py` — Streamlit auto-discovers it.

**New metric**: Add computation in `domain/analytics/` → include in the relevant DTO → render in a frontend widget.
