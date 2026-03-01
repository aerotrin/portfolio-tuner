# Portfolio Tuner

A full-stack portfolio tracking and analytics platform that combines **broker transaction history** with **live market data** to produce an accurate, computation-driven view of portfolio performance.

Unlike typical portfolio apps that rely only on current holdings, Portfolio Tuner reconstructs portfolio state from raw transaction records — enabling precise performance analysis and cost-basis accounting.

The system unifies two authoritative data sources:

1. **Broker ledger (Excel import)** — buys/sells, deposits/withdrawals, dividends, fees, taxes, interest, option exercises, splits, closed positions, and realized P&L
2. **Live market data** — quotes, historical OHLCV bars, and security profiles from configurable providers

Together they produce a real-time, historically-grounded portfolio view.

---

## Architecture at a Glance

![High level architecture](docs/images/arch_high.png)

Both services run in Docker containers orchestrated by `docker-compose`. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical design.

---

## Key Features

| Feature | Description |
|---|---|
| **Portfolio reconstruction** | Builds account state directly from raw transaction history — ACB tracking, open lots, cash flows |
| **Real-time valuation** | Combines ledger cost basis with live market quotes |
| **Performance metrics** | MWRR (IRR-based), Sharpe ratio, volatility, returns across any date range |
| **Technical indicators** | Timeseries indicators computed over historical OHLCV bars |
| **Correlation matrix** | Inter-security return correlation for holdings |
| **Portfolio simulation** | Monte Carlo simulation across random weight distributions to find the max-Sharpe frontier |
| **Market research pages** | ETF and stock screener views with movers, performance tables, and intraday chart |
| **Transaction entry** | Manual transaction recording and broker Excel import |
| **Background refresh jobs** | Async market data updates with real-time progress tracking |
| **Multi-account support** | Switch between accounts; each user's data is isolated at the database level via RLS |
| **Options tracking** | Call and put positions tracked with intrinsic value, DTE, and breakeven |

---

## Running Locally

### Prerequisites

- Docker and Docker Compose
- A [Supabase](https://supabase.com) project (PostgreSQL + Auth)
- A Financial Modeling Prep API key (optional — yfinance can be used as primary)

### Setup

```bash
git clone https://github.com/aerotrin/portfolio-tuner.git
cd portfolio-tuner
cp .env.example .env
# Fill in the required environment variables (see below)
docker-compose up --build
```

| Service | URL |
|---|---|
| Frontend dashboard | http://localhost:8501 |
| Backend API (OpenAPI docs) | http://localhost:8000/docs |

### Required Environment Variables

```env
# Database
POSTGRES_URL=postgresql://...

# Supabase Auth
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<anon-key>
SUPABASE_JWT_PUBLIC_KEY=<jwt-public-key>

# Market data (optional — yfinance used if FMP not enabled)
ENABLE_FMP_AS_PRIMARY=false
FMP_API_KEY=
FMP_RATE_LIMIT=100

# Concurrency
MAX_CONCURRENCY=5
```

### Symbols Configuration

The market research pages and benchmark lists are driven by `src/frontend/shared/symbols.yml`. Edit this file to add or remove symbols, grouped by category. See the file for detailed instructions.

---

## Project Structure

```
portfolio-tuner/
├── src/
│   ├── backend/                   # FastAPI application (uv package)
│   │   ├── domain/                # Entities, aggregates, analytics
│   │   ├── application/           # Use cases and port interfaces
│   │   ├── infra/                 # Adapters, API routers, DB models
│   │   └── shared/                # Config, logging
│   └── frontend/                  # Streamlit application (uv package)
│       ├── pages/                 # Multi-page app pages
│       ├── services/              # API client, cached data loaders
│       ├── shared/                # Config, dataframe helpers, job management
│       └── widgets/               # All UI rendering components
├── docs/                          # Additional documentation
├── docker-compose.yml
└── pyproject.toml                 # uv workspace root
```

---

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — Full technical design and engineering rationale
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — Dashboard user guide with user flow

---

## License

MIT License
