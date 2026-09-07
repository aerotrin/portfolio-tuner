# Portfolio Tuner — Dashboard User Guide

This guide walks through the complete user flow for Portfolio Tuner: from first login to a fully populated portfolio view with market data.

---

## Table of Contents

1. [Signing In](#1-signing-in)
2. [Disclaimer](#2-disclaimer)
3. [Creating Your First Account](#3-creating-your-first-account)
4. [Importing Transaction Records](#4-importing-transaction-records)
5. [The Sidebar](#5-the-sidebar)
6. [The Portfolio Page](#6-the-portfolio-page)
   - [Optimization Tab](#optimization-tab)
   - [All Accounts View](#all-accounts-view)
7. [Market Research Pages](#7-market-research-pages)
8. [Recording a Transaction Manually](#8-recording-a-transaction-manually)
9. [Refreshing Market Data](#9-refreshing-market-data)
10. [Account Management](#10-account-management)

---

## 1. Signing In

On first load, the dashboard shows a login form.

- Enter your email and password (registered via Supabase Auth).
- Click **Sign In**.

Authentication is handled by Supabase. The dashboard stores your session token and silently refreshes it on each page interaction. If your session fully expires, you will be redirected back to the login screen automatically.

> **Screenshot placeholder — Login screen**

---

## 2. Disclaimer

On first login (once per session), a disclaimer dialog appears confirming that Portfolio Tuner is for informational and educational purposes only and does not provide financial or investment advice.

- Click **I Understand** to proceed.
- The full disclaimer text is available on the **About** page.

> **Screenshot placeholder — Disclaimer dialog**

---

## 3. Creating Your First Account

If no accounts exist for your user, the dashboard shows a prompt to create one. You can also create additional accounts at any time from the sidebar.

**Fields:**
- **Account Number** — your brokerage account number (used as the ledger key); letters, digits, hyphens, and underscores are allowed (e.g. `ACC-001`)
- **Account Holder** — name of account holder
- **Account Type** — e.g. RRSP, TFSA, Non-Registered, Margin
- **Currency** — CAD or USD
- **Tax Status** — Registered or Non-Registered
- **Benchmark** — the index symbol to compare performance against (e.g. `^GSPC`, `^IXIC`)

Click **Create** to save. The account will appear immediately as a page link under **Accounts** in the navigation.

> **Screenshot placeholder — Create account dialog**

---

## 4. Importing Transaction Records

Once an account exists, populate it with transaction history by importing your broker's ledger export.

**Steps:**
1. On the **📊 Portfolio** page, select the account you want to populate (this makes it the active account).
2. Click the **Upload** icon button (import records) in the sidebar's account operations row.
3. In the dialog, click **Browse files** and select your `.xlsx` export file.
4. Click **Import**.

The importer parses all transactions from the file and upserts them into the database. Existing transactions are matched and updated; new ones are added. After a successful import, the page reloads automatically.

> **Screenshot placeholder — Import records dialog with file uploader**

> **Screenshot placeholder — Post-import portfolio page showing populated holdings**

**Supported transaction types in the ledger file:** Buy, Purchase, Sell, Sold, Split, Disburse, Expired, Redeemed, Exchange, Contrib, EFT, Transfer, Transf In, Withdrawal, Dividend, Interest, Return of Capital, Tax, HST, Fee.

---

## 5. The Sidebar

The sidebar is always visible and provides global controls that affect all pages.

### Active Account

The **📊 Portfolio** page (under **Accounts** in the navigation) hosts an account selector at the top of the page: **All Accounts** plus one option per account, listed by type and number. Selecting an account makes it the active account. The sidebar shows the active account label — the account operations, **Record Transaction**, and benchmark controls all apply to it. Choosing **All Accounts** (or visiting the market research pages) keeps the last-selected account active for those controls.

### Benchmark Selection

A dropdown lets you choose the benchmark index to compare portfolio performance against. The list is populated from the `benchmarks` section of `symbols.yml`. The account's default benchmark is pre-selected.

### Account Operations

A row of icon buttons provides account management:

| Button | Action |
|---|---|
| **+** (add) | Create a new account |
| **Upload** | Import transaction records from an Excel file |
| **Edit** | Edit the selected account's settings |
| **Delete** | Delete the selected account (with confirmation) |

### Record Transaction

The **Record Transaction** button (prominent, full-width) opens the manual transaction entry dialog. The dialog has its own account selector, pre-filled with the active account — you can switch the target account without leaving the form. See [Section 8](#8-recording-a-transaction-manually).

### Data Refresh

The **Force Refresh Data** button triggers a full re-fetch of all market data for the current page's symbols, bypassing the smart sync state. Use this when data appears stale or after adding new symbols to `symbols.yml`. (For routine background updates, use the **Auto Refresh** toggle at the top-right of each page instead — see [Section 9](#9-refreshing-market-data).)

### Hide Balances

The **Hide Balances** toggle masks the account identity and dollar amounts in the Account Summary KPI row (and the cash/securities donut hover) — useful for screen-sharing or demos. On the Positions tab, it also masks dollar figures in the KPI strip and treemap tiles/tooltips, and hides value-revealing columns (Quantity, Day P/L, Mkt Value, Total P/L, Book Value, FX Exposure, Intrinsic Value) from the positions tables. Percentage figures (returns, MWRR, cash %, weights) remain visible.

---

## 6. The Portfolio Page

The **📊 Portfolio** page (under **Accounts** in the navigation) is the main dashboard and the landing page after login. A selector at the top switches the whole page — summary KPIs and every tab — between **All Accounts** (the combined view, the default) and any single account. The sections below describe the single-account view; the [All Accounts view](#all-accounts-view) differences are covered at the end.

### Market Data Availability Check

When the page loads, it checks whether all required symbols have cached market data. If any symbols are missing, an automatic blocking refresh job starts and a progress bar is shown. The page completes loading once the job finishes.

---

### Status Strip

A compact strip at the top of the page shows global market context:

- Current date and time
- CAD/USD exchange rate
- Risk-free rate (6-month T-Bill)
- Data recency badge (right-hand side) — **Refreshed …** shows how long ago market data was last refreshed for this page (blue when under an hour old, yellow when staler). Until the first refresh completes for the page in the session, a gray **Last trade …** badge shows the latest quote last-trade time instead.

> **Screenshot placeholder — Status strip**

---

### Account Summary

Key performance indicators for the selected account (dollar amounts and account identity masked when Hide Balances is active):

| KPI | Description |
|---|---|
| **Total Value** | Market value of all positions plus cash balance |
| **Cash** | Current cash in the account |
| **Securities** | Market value of open positions |
| **Unrealized P/L** | Market value minus book value |
| **Return** | Unrealized gain as a percentage of book value |
| **MWRR** | Money Weighted Rate of Return (IRR-based, accounting for timing of deposits/withdrawals) |

> **Screenshot placeholder — Account summary KPI row**

---

### Market Snapshot

A header row showing current quotes for the symbols listed under `snapshot` in `symbols.yml` — typically major indices, gold, silver, and crude oil. Each cell shows the intraday price, day change and 1Y price history.

> **Screenshot placeholder — Market snapshot strip**

---

### Holdings Positions Table

A detailed view of all open positions in the account. A toggle in the section header switches between two views: **Intraday** and **Holdings**.

**KPI summary bar (both views):**

| KPI | Description |
|---|---|
| **Market Value** | Total market value of all open positions, with today's aggregate intraday change |
| **Best Intraday** | The holding with the largest intraday gain today |
| **Worst Intraday** | The holding with the largest intraday loss today |
| **Total FX Exposure** | Sum of USD-denominated position values converted to CAD |
| **No. of Holdings** | Count of open positions |
| **Average Days Open** | Mean calendar days positions have been held |

**Intraday view:**

- **Treemap** — tiles sized by portfolio weight and coloured by intraday percentage change (red–yellow–green). Each tile shows the current price, day change, volume, and last trade timestamp.
- **Health bar** — a row of green/red squares summarising how many securities are advancing vs. declining today.
- **Quote table** — one table for Stocks & ETFs and, if applicable, a second for Options. Columns: Symbol, Name, 1Y price sparkline, Signal, Price, Currency, Change, Change %, Volume, Prev. Close, High, Low, Exchange, Last Trade.

**Holdings view:**

- **Treemap** — tiles sized by portfolio weight and coloured by total unrealised gain/loss percentage. Each tile shows market value (CAD), total P/L, share count (or contract count for options), and days held (or DTE for options).
- **Health bar** — green/red squares showing how many positions are in profit vs. loss on a total-return basis.
- **Stocks & ETFs table** — Columns: Symbol, Name, 1Y sparkline, Quantity, Price, Currency, Day Change, Day P/L (CAD), Market Value (CAD), Total P/L (CAD), Total P/L %, Days Held, Weight %, Break-even Price, Book Value (CAD), FX Exposure, Type, Open Date, Last Trade.
- **Options table** (if options are held) — Columns: OSI, Name, 1Y sparkline, Quantity, Right, DTE, Intrinsic Value ⚠️, Break-even Price, Weight %, Total P/L (CAD), Total P/L %, Market Value (CAD), Book Value (CAD), Expiry, Strike, Last Price, FX Exposure, Days Held, Type, Open Date, Last Trade.

> **Note:** Option market value and P/L are calculated from intrinsic value only, not the actual contract price. Intraday change for options is not supported.

> **Screenshot placeholder — Holdings positions table — Intraday view**

> **Screenshot placeholder — Holdings positions table — Holdings view**

---

### Performance Tab

A tabbed view with performance analytics:

- **Growth chart** — normalised price history of holdings vs. the selected benchmark
- **Performance metrics table** — Sharpe ratio, CAGR, volatility, max drawdown, Sortino, Calmar for each holding and the portfolio
- **Signal display options** — toggle additional overlays (e.g., trade signals) on the chart

> **Screenshot placeholder — Performance tab with growth chart and metrics table**

---

### Allocation

A visual breakdown of portfolio allocation by market value:

- Treemap or pie chart showing each position's weight

> **Screenshot placeholder — Allocation chart**

---

### Optimization Tab

Runs a Monte Carlo simulation over random weight combinations drawn from the current holdings, then displays the simulated Efficient Frontier and the portfolio that best satisfies the selected objective.

**Form controls:**

| Control | Description |
|---|---|
| **Data Source** | Fixed to *Holdings* — the optimizer always uses current positions |
| **Iterations (n)** | Slider 1 000 – 5 000; more iterations improve frontier resolution |
| **Seed** | Optional integer 0–100 for reproducible runs; leave blank for a random seed |
| **Run Optimizer** | Triggers the backend simulation |

**Optimization metric** (selector shown after a run):

Switches the optimal portfolio view without re-running the simulation.

| Metric | Objective |
|---|---|
| Sharpe Ratio | Maximise |
| Sharpe (1M) | Maximise |
| Sharpe (3M) | Maximise |
| Volatility | Minimise |
| Max Drawdown | Minimise severity |
| Return 1Y | Maximise |

Sharpe (1M) and Sharpe (3M) favour recent risk-adjusted performance: the trailing 1-month or 3-month excess return over the annual volatility rescaled to that window (the same definition as the risk chart's period Sharpe).

**Results sections:**

- **KPI Summary** — three metric cards for the optimal portfolio, each with a delta vs. the actual portfolio. The return and volatility cards follow the selected metric's window: Sharpe (1M) shows Return (1M) and Volatility (1M), Sharpe (3M) the 3M equivalents; other metrics show the 1Y values.
- **Asset Allocation Comparison** — table of Actual / Optimal / Delta weights per symbol. Actual weights reflect current holdings at market value; optimal weights assume full investment with no cash allocation.
- **KPI Comparison** — three-row table (Actual / Optimal / Delta) for the displayed metrics
- **Efficient Frontier chart** — interactive scatter of all simulated portfolios coloured by Sharpe ratio (viridis scale). When a period Sharpe metric is selected, the whole chart rescales to that window — volatility axis scaled by √(days/252), period returns on the y-axis, and the risk-free line and CAL in period units. Overlays:
  - Current holdings position (■ square)
  - Optimal portfolio (◆ diamond, cyan)
  - Selected benchmark with crosshairs (magenta)
  - Capital Allocation Line from the risk-free rate through the max-Sharpe tangency portfolio (orange dashed)
  - Risk-free rate (horizontal dashed)

The chart footer records the run timestamp, seed, iteration count, run context (account or Research), and symbol count, and is embedded in any saved PNG snapshot. The same context stamp appears as a caption above the results.

> **Note:** Optimizer results are stored per account (and per research page) for the session — switching accounts shows that account's own last run, if any.

> **Screenshot placeholder — Optimization tab with efficient frontier chart**

---

### Correlation Matrix

A heatmap showing pairwise return correlation between all holdings. Values close to 1 indicate highly correlated securities; values close to -1 indicate inverse correlation. Useful for understanding diversification.

> **Screenshot placeholder — Correlation matrix heatmap**

---

### Records & Reports

A tabbed section showing the raw ledger data for the account:

- **Transactions** — full transaction history (type, date, symbol, quantity, price, amount, fees)
- **Closed Lots** — positions that have been fully sold or expired, with realised gain/loss
- **Cash Flows** — external cash movements (contributions, withdrawals) used for MWRR calculation

> **Screenshot placeholder — Transactions table**

---

### All Accounts View

Selecting **All Accounts** in the page selector (the default) combines every account into a single view with the same layout — summary KPIs, market snapshot, and all tabs — computed over your holdings across all accounts:

- **Weights and contributions** are a share of the *combined* total value. A symbol held in several accounts appears once per account with that account's own quantity, book value, and average cost — the Positions tab shows an **Account** column and treemaps grouped by account.
- **Allocation** adds a **By Account** pie chart showing each account's share of the combined portfolio value (securities + cash) alongside the instrument, currency, and holding breakdowns.
- **MWRR** pools external cash flows (contributions and withdrawals) from every account — it is a true money-weighted return on all invested capital, not an average of per-account MWRRs.
- **Correlation** covers all pairs across accounts, including pairs of symbols held in different accounts.
- **Optimization** runs over the combined symbol list with its own saved result, separate from each account's optimizer runs.

Cash held in USD-denominated accounts is converted to CAD at the current exchange rate. The Records tab shows ledger data only when a single account is selected; the sidebar **Record Transaction** form opens on the active (last-selected) account, has its own in-form account selector, and always validates against the chosen account's own cash and holdings.

> **Screenshot placeholder — All Accounts view**

---

## 7. Market Research Pages

### ETF Research (`🏦 ETF Research`)

A standalone research dashboard for the ETF symbols configured in `symbols.yml` under `base_market_etfs`.

**Sections:**
- **Status strip** — global rates and the last-refreshed indicator
- **Market snapshot** — header quotes
- **Market movers** — most active, top gainers and losers for the US or Canadian market. If no data is available for a symbol group, or if market conditions produce no gainers or losers in a category, an informational message is shown in place of the table.
- **Intraday tab** — a market-map treemap of every configured symbol, nested region → group → symbol, with a health bar and quote table. Click a region tile to zoom into it; optional type and group filters narrow the map
- **Performance tab** — growth chart, risk/return chart and performance metrics table, filtered by the Region → Type → Group facets (see below)
- **Correlation tab** — correlation matrix heatmap and strongest/weakest pair tables for the securities currently in scope on the Performance tab (facet filter, refined by any table row selection)
- **Optimization tab** — runs the same Monte Carlo weight optimizer as the Portfolios page, over the securities currently in scope on the Performance tab. Results are stamped "Research" with the symbol count and kept per page; if the selection changes after a run, a notice prompts a re-run. A warning appears above 25 symbols (random weight sampling becomes less meaningful) and runs are blocked above 50 — narrow the selection first.

Use the date range selector to change the historical window for charts and metrics.

**Filtering by region, type and group**

The Performance tab is filtered by the group taxonomy defined in `symbols.yml`, across three levels: Region and Type narrow each other (choosing **Fixed Income** leaves only the regions that have some), and together they narrow the group list. Leaving a level empty means "all", so clearing every level shows the full symbol universe. If a selection is invalidated by a change higher up — picking Canada while a US-only group was selected — the stale choice is dropped rather than leaving you with an empty table, and the **Clear** button resets the whole filter in one click.

The Intraday tab takes the opposite approach: instead of filtering, the treemap *shows* the taxonomy — regions as parent tiles, groups within them, symbols within groups. Click a region tile to zoom in, or narrow the map with the type pills (one-click asset-class slice, e.g. **Fixed Income**) and the group filter for the fine cut. The two tabs keep independent state.

> **Screenshot placeholder — ETF Research page with movers table**

> **Screenshot placeholder — ETF performance tab**

> **Screenshot placeholder — ETF correlation tab**

---

### Stocks Research (`🏦 Stocks Research`)

Identical in structure to the ETF page but for the stock symbols configured under `base_market_stocks` (e.g., Magnificent 7, NASDAQ 100, S&P 100, Dow 30, TSX 60).

> **Screenshot placeholder — Stocks Research page**

---

## 8. Recording a Transaction Manually

Click **Record Transaction** in the sidebar to open the transaction entry form.

**Fields:**
- **Account** — a selector at the top of the form, pre-filled with the active account each time the form opens. Switching it reloads the form in place for the chosen account: the SELL symbol list, maximum quantities, cash-available figure, and trade-sizing guide all update — no need to close the form and change the page selection first.
- **Transaction Type** — Buy, Sell, or EFT (other types, such as Return of Capital, arrive via the Excel ledger import)
- **Symbol** — security ticker (optional for cash transactions)
- **Date** — transaction date
- **Quantity** — number of shares/units
- **Price** — price per unit
- **Currency** — CAD or USD
- **Amount** — total transaction amount (positive for inflows, negative for outflows)
- **Commission** — brokerage commission
- **Fees** — additional fees

Click **Submit** to save. The portfolio view updates on the next page load.

> **Screenshot placeholder — Transaction form dialog**

---

## 9. Refreshing Market Data

Market data (quotes, historical bars, profiles) is cached in the database and must be refreshed periodically to stay current.

### Automatic Refresh (Smart Sync)

The system automatically checks symbol availability on each page load. If any required symbols are missing from the cache, a blocking refresh job starts automatically and the page waits for it to complete before rendering.

On subsequent loads, the smart sync only fetches data newer than the last successful bar date for each symbol — making incremental refreshes fast.

### Auto Refresh Toggle

The **Auto Refresh** toggle — next to the **Refresh Data** button at the top-right of each page — re-runs the incremental smart sync for the current page's symbols on a fixed interval (default 5 minutes, set via `AUTO_REFRESH_DATA_INTERVAL` in milliseconds). The setting carries across pages, and each page scope keeps its own refresh cycle: the two market research pages are tracked separately (they cover many symbols and take longer), while all account portfolio pages share one scope — a portfolio refresh covers the holdings of **every** account plus the benchmark/header symbols, so switching between accounts always shows current data. A refresh fires immediately — without waiting for the next cycle — whenever the toggle is on and the current page's scope hasn't been refreshed yet this session (shown by the gray **Last trade** badge): both when you switch the toggle on and when you first open such a page. Refreshes run in the background — the page stays fully interactive and updates once with fresh data when each job completes.

### Manual Refresh

Two manual refresh options are available:

| Button | Location | Behaviour |
|---|---|---|
| **Refresh Data** | Top-right of each page | Re-runs smart sync for the current page's symbols (incremental), in the background — the page stays interactive |
| **Force Refresh Data** | Sidebar | Re-fetches the full date range for all current page symbols, ignoring sync state (blocks the page while running) |

On the Portfolio page, "the current page's symbols" means the holdings of **all** your accounts plus the benchmark/header symbols — one refresh keeps every account scope current. Market research pages refresh only their own symbol lists.

Use **Force Refresh Data** when quotes appear stale, after changing the date range significantly, or after adding new symbols to `symbols.yml`.

### Refresh Progress

Background refreshes (the **Refresh Data** button and the **Auto Refresh** toggle) show a live progress bar under **Refresh Status** at the bottom of the sidebar; the page reloads with fresh data when the job finishes.

Blocking refreshes (missing-symbol bootstrap and **Force Refresh Data**) show a progress banner at the top of the page and pause rendering until the job completes.

> **Screenshot placeholder — Refresh job progress banner**

---

## 10. Account Management

### Editing an Account

Click the **Edit** (pencil) button in the sidebar's account operations row to open the edit dialog. You can update the account name, type, currency, tax status, and benchmark. The account number cannot be changed after creation.

> **Screenshot placeholder — Edit account dialog**

### Deleting an Account

Click the **Delete** (trash) button in the sidebar's account operations row. A confirmation dialog warns that all transactions and account records will be permanently deleted. This action cannot be undone.

> **Screenshot placeholder — Delete confirmation dialog**

### Logging Out

Click the **Logout** button at the bottom of the sidebar. Your session is terminated and you are returned to the login screen. Session state is fully cleared.

---

## Tips

- **Date range controls** — the start and end date selectors (visible on each page) control the historical window for charts and performance metrics. Changes take effect on the next page interaction.
- **Hide Balances** — use the sidebar toggle to mask monetary values, quantities, and account identity during screen-sharing; percentage figures stay visible.
- **Multiple accounts** — each account has its own page link in the navigation; click to jump directly between accounts. Each account is independently tracked.
- **Benchmark** — changing the benchmark in the sidebar updates the comparison series on growth charts and performance metrics in real time.
- **symbols.yml** — to add or remove symbols from the market research pages, edit `symbols.yml` in the project root and restart the frontend. No code changes are required. Each group takes a `label` plus an optional `type` (Equity, Fixed Income, Multi-Asset, Commodity, Crypto, Forex, Index) and `region` (US, Canada, World, N/A); these drive the Region and Type filters on the market pages. The label names a concept and is meant to repeat across regions — "Core" can exist under US, Canada and World. Only the region + type + label combination must be unique. The group filter lists each label once: selecting "Sectors" with no region chosen gives you every region's sectors, and you narrow to one by picking a region. Both are optional — groups without them fall back to `Other` and `N/A` — and any other value is accepted, sorting after the suggested ones. They are labels for filtering only and are never checked against a symbol's exchange or actual holdings.
