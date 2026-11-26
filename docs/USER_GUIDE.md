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
   - [Managing GICs and Term Deposits](#managing-gics-and-term-deposits)
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

The importer parses all transactions from the file and replaces the account's transactions with them, so the account always matches the file. Anything entered by hand in that account, including GICs and term deposits added from the sidebar, is removed; the import dialog warns you when that applies. After a successful import, the page reloads automatically.

> **Screenshot placeholder — Import records dialog with file uploader**

> **Screenshot placeholder — Post-import portfolio page showing populated holdings**

**Supported transaction types in the ledger file:** Buy, Purchase, Sell, Sold, Split, Disburse, Expired, Redeemed, Exchange, Contrib, EFT, Transfer, Transf In, Withdrawal, Dividend, Interest, Return of Capital, Tax, HST, Fee.

**GICs in the ledger file:** import the bank's rows as they are. A GIC's Buy, Interest and Redeemed rows have no symbol; the app recognises them from the description (`... Maturity NOV 07 2024 Coupon 5.00 ...`) and reads the maturity date and rate from it. The issue date is taken as the purchase's settlement date, and interest is assumed to be simple. If a fixed-income row's description has no maturity and coupon the app can read, the holding is kept at its purchase cost and labelled *terms unknown*.

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

### Manage GIC / Term Deposit

The **Manage GIC / Term Deposit** button opens one dialog with three actions: **Add** a GIC or term deposit from its terms (principal, rate, issue date, term, interest schedule), **Record redemption**, and **Record interest**. See [Managing GICs and Term Deposits](#managing-gics-and-term-deposits).

### Data Refresh

The **Force Data Refresh** button triggers a full re-fetch of all market data for every symbol across all pages (after a confirmation dialog showing the symbol count), bypassing the smart sync state. Use this when data appears stale or after adding new symbols to `symbols.yml`. (For routine background updates, use the **Auto** (auto refresh) toggle at the top-right of each page instead — see [Section 9](#9-refreshing-market-data).)

### Export Summary

The **Export Summary** button downloads an Excel workbook (`portfolio_summary_<scope>_<date>.xlsx`, one sheet named `Summary`) listing every constituent of the portfolio shown on the Portfolio page: all accounts when the selector is on **All Accounts**, or just the selected account. It is meant for importing into another workbook that rolls up positions by account, so every row has the same columns whatever the asset type:

| Column | Meaning |
|---|---|
| As Of | Date of the export |
| Account Number, Account Type | The owning account |
| Asset Type | Stock, ETF, Call Option, Put Option, GIC, Term Deposit, Cash, … |
| Symbol | Ticker; the OSI contract code for options; the instrument key for GICs and term deposits; `CASH` for cash |
| Security Name | Security name; `AAPL Jan 15 2027 150 Call` style for options; the instrument label for GICs and term deposits |
| Currency | The security's own currency (the account's ledger currency for cash) |
| Quantity | Units held (blank for cash) |
| Book Value (CAD), Market Value (CAD), Unrealized P/L (CAD), Unrealized P/L % | Same values as the Positions tab |
| Weight | Share of the exported portfolio's total value, cash included |

Each account also gets one **Cash** row (negative for a margin balance), so Market Value adds up to the portfolio's total value and Weight adds up to 100%. Rows are sorted by account, then symbol, with cash last.

The button is active on the Portfolio page only. The file always contains real account numbers and values, even when **Hide Balances** or **Hide Account Numbers** is on.

### Hide Balances

The **Hide Balances** toggle masks the dollar amounts in the Account Summary KPI row (and the cash/securities donut hover) — useful for screen-sharing or demos. On the Positions tab, it also masks dollar figures in the KPI strip and treemap tiles/tooltips, and hides value-revealing columns (Quantity, Day P/L, Mkt Value, Total P/L, Book Value, FX Exposure, Intrinsic Value, Cash, Cash CAD) from the positions tables; the Cash by Account donut keeps its percentages but masks the total. On the Allocation tab, it removes dollar values from chart tooltips and the Breakdown table and masks the position sizing guide. Percentage figures (returns, MWRR, cash %, weights) remain visible.

### Hide Account Numbers

The **Hide Account Numbers** toggle is independent of Hide Balances. When on, every account label keeps only the last two digits of the number (`TFSA #12345` becomes `TFSA ••45`) and the owner name is masked. This applies to the account selector, the Account Summary, the Account column and treemap groups on the Positions tab, the Cash table and Cash by Account donut, the Account breakdown and Asset mix by account charts on the Allocation tab, the sidebar, and the account picker in the Record Transaction dialog. If two accounts of the same type share their last two digits, more digits are shown for those accounts so they stay distinct.

---

## 6. The Portfolio Page

The **📊 Portfolio** page (under **Accounts** in the navigation) is the main dashboard and the landing page after login. A selector at the top switches the whole page — summary KPIs and every tab — between **All Accounts** (the combined view, the default) and any single account. The sections below describe the single-account view; the [All Accounts view](#all-accounts-view) differences are covered at the end.

### Market Data Availability Check

When the page loads, it checks whether all required symbols have cached market data. If any symbols are missing, an automatic blocking refresh job starts and a progress bar is shown. The page completes loading once the job finishes.

---

### Header Rows

The Portfolio page packs its header into two rows. The first row shows a compact page title on the left and, right-aligned, today's date and time, the **FX Rate** (USD/CAD), the **Rf Rate** (risk-free US Treasury bill yield; hover either label for a description), the data recency badge, and the **Auto** (auto refresh) toggle. The second row holds the account selector on the left and the **Refresh Data** button on the right.

The recency badge — **Refreshed …** — shows how long ago market data was last refreshed for this page (blue when under an hour old, yellow when staler); hover for the exact timestamp. Until the first refresh completes for the page in the session, a gray **Last trade …** badge shows the latest quote last-trade time instead. The date and time are shown in your browser's timezone. They and the recency badge update every 30 seconds without reloading the page.

The market research pages use the same single-row pattern: page title on the left, with the date and time, rates, recency badge, **Auto** toggle, and **Refresh Data** button clustered on the right.

> **Screenshot placeholder — Portfolio header row**

---

### Account Summary

Key performance indicators for the selected account (dollar amounts are masked when Hide Balances is active; the account number and owner when Hide Account Numbers is active):

| KPI | Description |
|---|---|
| **Total Value** | Market value of all positions plus cash balance, with today's aggregate intraday change (dollars and percent) as the delta. Positions whose quote has no published day change yet (e.g. premarket) contribute zero to that delta |
| **Securities Value** | Market value of open positions, with the unrealized P/L (dollars) and return on book value (percent) as the delta |
| **Cash / Securities donut** | Share of the portfolio held as securities vs. cash |
| **Cash** | Current cash in the account, with its share of the portfolio as the delta |
| **Total Return** | Total value minus net investment, with MWRR (IRR-based, accounting for timing of deposits/withdrawals) as the delta |

When Hide Balances is on, the dollar deltas are masked but the percentages stay visible.

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
| **Best Intraday** | The holding with the largest intraday gain today |
| **Worst Intraday** | The holding with the largest intraday loss today |
| **Total FX Exposure** | Sum of USD-denominated position values converted to CAD |
| **No. of Holdings** | Count of open positions |
| **Average Days Open** | Mean calendar days positions have been held |

**Intraday view:**

- **Treemap** — tiles sized by portfolio weight and coloured by intraday percentage change (red for down, light grey for flat, green for up; full colour at ±4% or more). Each tile shows, in order: current price, day change, volume (`Vol. 1.2M · 1.5×`), portfolio weight (`Wt. 15.88%`) and last trade time. The ⓘ after the securities count under the map explains the colours and the volume figures.
- **Health bar** — a row of green/red squares summarising how many securities are advancing vs. declining today.

**Holdings view:**

- **Treemap** — tiles sized by portfolio weight and coloured by total unrealised gain/loss percentage (same red–grey–green scale, full colour at ±25% or more). Each tile shows, in order: market value (CAD), total P/L, shares and holding age as five dots (`350 sh · ●●●○○`: one dot under a month, then 3 months, 6 months and a year, all five at a year or more; exact days on hover, and the ⓘ after the positions count under the map gives a key to the colours and dots; contracts and DTE for options, `2 ct · 30 DTE`), portfolio weight and last trade time. The rows line up with the Intraday view, so toggling swaps the first three rows in place and leaves weight and trade time where they are.
- **Health bar** — green/red squares showing how many positions are in profit vs. loss on a total-return basis.
- **Cash table** — one row per account, listed above the securities tables (shown even when the account holds no positions). Columns: Account, Currency, Cash (in the account's own currency), Cash CAD, % of Account (cash as a share of that account's total value), Weight % (share of the portfolio's total value). Negative cash is shown in red. In **All Accounts** scope a caption totals the cash across accounts, and when more than one account holds cash a **Cash by Account** donut shows each account's share.
- **Row shading** — in the Stocks & ETFs, Options and Fixed Income tables, a row is shaded green when the position's total gain is +25% or more (take-profit level) and red at −10% or worse (stop-loss level); gain and change figures are coloured green or red by sign. The ⓘ next to **Holdings** explains this. The levels are `TAKE_PROFIT_LIMIT` and `LOSS_LIMIT` in `src/frontend/shared/settings.py` and are separate from the treemap colour scales.
- **Stocks & ETFs table** — live columns first, then the ones that rarely change. Columns: Symbol, Name, 1Y sparkline, Price, Day, Signal, Rel Vol, Day P/L (CAD), Total P/L (CAD), Total P/L %, Market Value (CAD), Weight %, Quantity, Days Held, Break-even Price, Book Value (CAD), FX Exposure, Type, Open Date, Last Trade. **Price** is shown with its currency (`611.68 USD`) and **Day** is the change since the previous close with an arrow (`▼ 4.14%`); both are green or red by today's move and still sort as numbers. **Rel Vol** is today's volume ÷ the 20-day average.
- **Options table** (if options are held) — Columns: OSI, Name, 1Y sparkline, Underlying, Und. Day, Right, DTE, Intrinsic Value ⚠️, Total P/L (CAD), Total P/L %, Market Value (CAD), Weight %, Quantity, Break-even Price, Book Value (CAD), Expiry, Strike, FX Exposure, Days Held, Type, Open Date, Last Trade. **Underlying** and **Und. Day** are the underlying security's price and change today, shown and coloured like Price and Day above.
- **Fixed Income table** (if GICs or term deposits are held) — Columns: Name, Status (Active or Matured), Rate, Interest Paid, Weight %, Principal, Currency, Maturity, Days to Maturity, Accrued Interest, Interest Received, Value (CAD), Maturity Value, Total P/L (CAD), Total P/L %, Book Value (CAD), FX Exposure, Issue Date, Days Held, Type, Key. The table is read-only: to record a redemption or an interest payment, use **Manage GIC / Term Deposit** in the sidebar (see [Managing GICs and Term Deposits](#managing-gics-and-term-deposits)).

Click a symbol in the Stocks & ETFs table, or an OSI in the Options table, to open the [daily price chart](#daily-price-chart) (an option opens the chart of its underlying).

> **Note:** Option market value and P/L are calculated from intrinsic value only, not the actual contract price. Intraday change for options is not supported.

> **Note:** A GIC or term deposit has no market price. Its value is the principal plus the interest earned to date that has not been paid out, so it rises a little every day until maturity. Interest is counted from the issue date up to and including today, which is how banks report a deposit's current value. It appears in both treemaps, the KPIs and all portfolio totals. In the Intraday treemap it is a neutral tile of the same size as in Total Return, so the layout stays the same when you toggle between the two views. Its tile shows value, total P/L (`No intraday chg` in the Intraday view), rate and time left (`2.45% · 15 d left`, or `matured`), weight and maturity date (`Mat. 2026-12-09`). It is left out of the Best/Worst Intraday KPIs, the up/down bar under the Intraday treemap and the quote table.

> **Screenshot placeholder — Holdings positions table — Intraday view**

> **Screenshot placeholder — Holdings positions table — Holdings view**

---

### Performance Tab

A tabbed view with performance analytics:

- **Growth chart** — normalised price history of holdings vs. the selected benchmark
- **Performance metrics table** — Sharpe ratio, CAGR, volatility, max drawdown, Sortino, Calmar for each holding and the portfolio
- **Signal display options** — toggle additional overlays (e.g., trade signals) on the chart
- **Daily price chart** — click a symbol in the Securities or Benchmark table to open its [daily price chart](#daily-price-chart). Ticking a row's checkbox still narrows the charts above; only a click on the symbol itself opens the chart

GICs and term deposits count in the **Portfolio** line and statistics as a steady asset, which lowers portfolio volatility in proportion to their weight. They are not listed as securities and have no line of their own; a note under the Securities table names them. An account holding only fixed income shows near-zero volatility and a Sharpe ratio that is not meaningful.

> **Screenshot placeholder — Performance tab with growth chart and metrics table**

---

### Allocation

Shows how the portfolio is spread, how concentrated it is, and where its risk comes from. All shares are of holdings plus positive cash, in CAD.

- **Concentration row** — number of holdings, the largest position and top 5 as a share of invested holdings, **Effective holdings** (how many equal-sized positions would be as concentrated as yours; the further below the holdings count, the more a few positions dominate), cash share, and USD exposure (USD-quoted holdings plus cash in USD accounts).
- **Breakdown** — a donut with a selector for **Asset type**, **Instrument** (equity, call/put option, fixed income, cash), **Sector**, **Country**, or **Currency**, with a table of the same figures underneath. ETFs without sector or country data are grouped as *ETF / unclassified*; the app does not look inside funds.
- **Holdings by weight** — one bar per symbol, largest first. The top 15 are shown individually and the rest are combined as *Other*; cash has its own bar. Options are counted under their underlying at intrinsic value, and GICs and term deposits at their accrued value.
- **Capital vs risk** — each holding's weight next to its share of the portfolio's volatility over the past year of daily returns. A risk share well above the weight marks a position that drives more of the portfolio's swings than its size suggests. Holdings with too little price history are listed below the chart instead of being plotted. GICs and term deposits hold their value, so they show their weight with a risk share of zero.
- **Position sizing guide** — an expandable table of the dollar amount for a new position at 1% to 20% of the portfolio.

If an account's cash is negative (margin), it is left out of the shares and noted under the concentration row.

> **Screenshot placeholder — Allocation tab**

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

> **Note:** A security needs at least 40 days of price history within the past year to take part in a run. Securities with less are left out of the simulation and named in a note above the results; the optimal weights cover the remaining securities only.

> **Note:** Optimizer results are stored per account (and per research page) for the session — switching accounts shows that account's own last run, if any.

> **Screenshot placeholder — Optimization tab with efficient frontier chart**

---

### Correlation Matrix

A heatmap showing pairwise return correlation between all holdings. Values close to 1 indicate highly correlated securities; values close to -1 indicate inverse correlation. Useful for understanding diversification.

A security needs at least 40 days of price history within the past year to be included. Securities with less are left out of the heatmap and the pair tables, and are listed in a note above the matrix. GICs and term deposits have no market price to correlate and are listed in a separate note. The same applies on the **Optimization** tab, where they are not candidates.

> **Screenshot placeholder — Correlation matrix heatmap**

---

### Records & Reports

A tabbed section showing the raw ledger data for the account:

- **Transactions** — full transaction history (type, date, symbol, quantity, price, amount, fees)
- **Closed Lots** — positions that have been fully sold or expired, with realised gain/loss
- **Cash Flows** — external cash movements (contributions, withdrawals) used for MWRR calculation, and income and expenses. Interest paid by a GIC or term deposit carries that instrument's key in the Symbol column and is totalled as **Fixed Income Interest**; it is also part of **Interest Income**

> **Screenshot placeholder — Transactions table**

---

### All Accounts View

Selecting **All Accounts** in the page selector (the default) combines every account into a single view with the same layout — summary KPIs, market snapshot, and all tabs — computed over your holdings across all accounts:

- **Weights and contributions** are a share of the *combined* total value. A symbol held in several accounts appears once per account with that account's own quantity, book value, and average cost — the Positions tab shows an **Account** column and treemaps grouped by account.
- **Allocation** adds **Account** to the Breakdown selector (each account's share of the combined value, securities + cash) and an **Asset mix by account** chart showing what each account holds by asset type. Holdings by weight and Capital vs risk combine a symbol held in several accounts into one bar.
- **MWRR** pools external cash flows (contributions and withdrawals) from every account — it is a true money-weighted return on all invested capital, not an average of per-account MWRRs.
- **Correlation** covers all pairs across accounts, including pairs of symbols held in different accounts.
- **Optimization** runs over the combined symbol list with its own saved result, separate from each account's optimizer runs.

Cash held in USD-denominated accounts is converted to CAD at the current exchange rate (in both All Accounts and single-account scope; the Positions tab's Cash table also shows the original USD amount). The Records tab shows ledger data only when a single account is selected; the sidebar **Record Transaction** form opens on the active (last-selected) account, has its own in-form account selector, and always validates against the chosen account's own cash and holdings.

> **Screenshot placeholder — All Accounts view**

---

## 7. Market Research Pages

### ETF Research (`🏦 ETF Research`)

A standalone research dashboard for the ETF symbols configured in `symbols.yml` under `base_market_etfs`.

**Sections:**
- **Header row** — page title with date and time, global rates, the last-refreshed indicator, the Auto refresh toggle, and the Refresh Data button
- **Market snapshot** — header quotes
- **Market movers** — the most active securities, top gainers and losers for the US or Canadian market. A US / Canada selector right after the heading switches between the two; it is hidden when the page's symbols are all from one market, and each research page remembers its own choice. **Most Active** ranks by dollar volume (today's volume × price), so it shows where the most money traded rather than the highest share count. If no data is available for a symbol group, or if market conditions produce no gainers or losers in a category, an informational message is shown in place of the table.
- **Intraday tab** — a market-map treemap of every configured symbol, nested region → group → symbol, with a gainer/loser count and quote table. Click a region, group or symbol tile to zoom into it — the gainer/loser count and quote table narrow to match, and the Performance tab follows the same selection; optional type pills narrow the map. **Colour** shades tiles by change % (red–grey–green, full colour at ±4% or more) or by relative volume (today's volume ÷ 20-day average), and **Sort** independently orders the symbols inside each group — and the quote table — by change % or by dollar volume (value traded: today's volume × price, in the security's own currency), highest first; securities without volume sort last
- **Performance tab** — growth chart, risk/return chart and performance metrics table, filtered by a group multiselect that starts from the Intraday treemap selection (see below)
- **Price and Day columns** — every quote and performance table (here and on the Portfolio page) shows **Price** with its currency (`611.68 USD`) and **Day**, the change since the previous close, with an arrow (`▼ 4.14%`). Both are green or red by today's move and still sort as numbers
- **Correlation tab** — correlation matrix heatmap and strongest/weakest pair tables for the securities currently in scope on the Performance tab (group filter, refined by any table row selection). Securities with fewer than 40 days of price history are left out and listed in a note
- **Optimization tab** — runs the same Monte Carlo weight optimizer as the Portfolios page, over the securities currently in scope on the Performance tab. Results are stamped "Research" with the symbol count and kept per page; if the selection changes after a run, a notice prompts a re-run. A warning appears above 25 symbols (random weight sampling becomes less meaningful) and runs are blocked above 50 — narrow the selection first.

Use the date range selector to change the historical window for charts and metrics.

#### Daily price chart

Symbols shown in blue are clickable. Click one in any quote, performance or holdings table (Movers, Intraday, Performance, and the Portfolio page's Positions and Performance tabs) to open a pop-out chart of its daily prices. Checkboxes in the Performance table keep their role of filtering the charts.

| Control | What it does |
|---|---|
| **Symbol** | Switch to another symbol from the table you clicked in; type to search |
| **Range** | 5D, 1M, 3M, 6M, YTD, 1Y or MAX (up to two years). Ranges count trading sessions (5, 21, 63, 126, 252), so they match the Return columns in the performance tables |
| **Chart** | Candles or a line of closing prices |
| **Show** | Turn on or off: moving averages, Bollinger Bands (20-day, 2 standard deviations), the volume panel, the RSI 14 panel (band between 30 and 70), the MACD (12, 26, 9) panel, and price tags at the right edge |
| **⚙ settings** | Moving-average type (SMA or EMA) and up to five periods between 2 and 250 days; type a number to add your own. Default: SMA 20, 50 and 200 |

Above the chart: **Last** price with the change since the previous close, the change over the selected range (measured from the close before its first session), the 52-week high and low (from daily highs and lows over the last 252 sessions), today's volume and the market cap. A figure the provider does not supply shows as "—". The footer shows the last trade time in your browser's time zone.

Hover anywhere on the chart to read every panel's values for that day. Weekends and market holidays are left out, so candles sit side by side. Indicators are calculated over the whole stored history, so a moving average is complete from the left edge of a short range; an average that needs more history than is stored (for example SMA 200 on a recently listed security) is left off and noted under the chart. Your choices are remembered until you sign out, and the chart stays open while the page refreshes in the background.

> **Note:** Prices are the provider's adjusted daily prices, so historical candles and 52-week levels can differ slightly from unadjusted figures quoted elsewhere.

> **Screenshot placeholder — Daily price chart with volume, RSI and MACD panels**

**Filtering by region and group**

The Performance tab has one filter: a multiselect listing every group on the Intraday treemap, named by its region (**US / Sectors**). Pick several to compare them side by side, e.g. **US / Sectors** with **Canada / Sectors**, which the treemap cannot show at once. Leaving the filter empty shows every group. To narrow to individual securities, tick rows in the metrics table.

The filter starts from whatever the Intraday treemap is showing. Zoom into a region tile and the Performance tab opens on all of that region's groups, which you can then trim; zoom into a group (or a symbol within it) and it opens on that group. With the Intraday type pills active, it opens on the groups of those types — across the whole map, or within the region you zoomed into. With the map not zoomed and no type picked, it opens on the first group in `symbols.yml`. Your own changes to the filter stay until the next click on the treemap, which takes over again. The caption under the filter shows how many groups and securities are in scope and notes when the filter differs from the Intraday selection; **Reset** returns to it. The Correlation and Optimization tabs follow along, since they use the Performance tab's selection.

The Intraday tab takes the opposite approach: instead of filtering, the treemap *shows* the taxonomy — regions as parent tiles, groups within them, symbols within groups. Click a region or group tile to zoom in — the gainer/loser count and quote table below follow the zoom, down to a single row if you click one symbol, and clicking the top bar zooms back out and restores the full list. Or narrow the map first with the type pills (a one-click asset-class slice, e.g. **Fixed Income**); drilling then works within that slice, and the table heading shows both, e.g. *ETF Quotes (Fixed Income) · US / Core*. Changing the pills resets the zoom. The **Colour** control switches the tiles between **Change %** (red/green) and **Rel. volume** — today's volume divided by the security's own 20-day average, in shades of blue that are darkest at 3× or more — to show where trading is unusually heavy; the multiple also appears on each tile and in the table's **Rel Vol** column. It reads low early in the session because the day's volume is still accumulating, and securities with no traded volume (indices, FX) show no multiple. Switching colour keeps the zoom.

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

### Managing GICs and Term Deposits

Click **Manage GIC / Term Deposit** in the sidebar. The dialog works from any tab and any account scope. Pick the **Account** (pre-filled with the active account), then an **Action**: **Add**, **Record redemption** or **Record interest**. Switching account or action updates the dialog in place.

#### Add

Use this for a GIC or term deposit that is not in an imported ledger, for example one held directly at a bank.

**Fields:**
- **Type** and **Issuer** — GIC or Term Deposit, and the institution's name (shown as the holding's name).
- **Principal**, **Annual rate %**, **Currency**.
- **Issue date**, **Term**, **Maturity date** — choosing a term (30 days to 5 years) fills in the maturity date; edit the date directly for any other term.
- **Interest paid** — At Maturity, Annual, Semi-Annual, Quarterly or Monthly.
- **Interest calculation** — Simple, or Compounded annually (only when interest is paid at maturity).
- **Redeemability** — Non-redeemable or Redeemable (recorded with the holding; it does not change the valuation).
- **Paid from** — **Account cash** reduces the account's cash by the principal. **New deposit** records a matching deposit with the purchase, so cash is unchanged and the money counts as a contribution in your returns.

The preview shows the maturity date, the interest at maturity, the maturity value and the value today. Click **Add** to save.

*Example:* a 1-year non-redeemable GIC issued Dec 9, 2025 at 2.45% paid at maturity, principal $26,104.02, earns $639.55 and is worth $26,743.57 on Dec 9, 2026.

#### Record redemption

Nothing is posted automatically at maturity. From the maturity date the holding shows as **Matured** at its final value, with a notice above the Fixed Income table, until you record the redemption. Choose **Record redemption**, then the **Holding** (matured holdings are listed first). The form is pre-filled with the principal and the interest still owed; adjust either if the bank paid a different amount, then confirm. The principal and interest move to the account's cash and the holding closes. For a redeemable GIC cashed early, enter the principal redeemed and the interest actually paid.

#### Record interest

For a GIC that pays interest monthly, quarterly, semi-annually or annually, choose **Record interest** and the **Holding** each time a payment arrives. The amount defaults to the interest accrued and not yet received. Until a payment is recorded the app keeps counting that interest in the holding's value; the **Interest Received** column shows what has been recorded.

Only holdings whose terms are known can be picked. A fixed-income holding imported without recognisable terms is closed by its ledger rows instead.

> **Screenshot placeholder — Manage GIC / term deposit dialog**

---

## 9. Refreshing Market Data

Market data (quotes, historical bars, profiles) is cached in the database and must be refreshed periodically to stay current.

### Automatic Refresh (Smart Sync)

The system automatically checks symbol availability on each page load. If any required symbols are missing from the cache, a blocking refresh job starts automatically and the page waits for it to complete before rendering.

A symbol only needs a current quote to be shown. A **newly listed security** (for example on its IPO day) has no daily price history yet, so it appears with its price, market value, and weight straight away, while its performance columns (returns, volatility, Sharpe, correlation) stay blank and fill in as daily history builds up. It joins the correlation matrix once it has 40 days of price history. Until then it counts as flat in the portfolio's own performance figures, and an account holding only such securities shows "—" for its Performance statistics.

On subsequent loads, the smart sync only fetches data newer than the last successful bar date for each symbol — making incremental refreshes fast.

About two years of daily prices are kept per symbol (`BARS_HISTORY_DAYS` in `.env`, default 730 days). A symbol holding less than that is topped up with one full download on its next refresh, so the first refresh after an upgrade or after raising the setting takes longer than usual.

### Auto Refresh Toggle

The **Auto** toggle — just left of the **Refresh Data** button at the top-right of each page — re-runs the incremental smart sync for the current page's symbols on a fixed interval (default 5 minutes, set via `AUTO_REFRESH_DATA_INTERVAL` in milliseconds). The setting carries across pages, and each page scope keeps its own refresh cycle: the two market research pages are tracked separately (they cover many symbols and take longer), while all account portfolio pages share one scope — a portfolio refresh covers the holdings of **every** account plus the benchmark/header symbols, so switching between accounts always shows current data. A refresh starts within about ten seconds — without waiting for the next cycle — whenever the toggle is on and the current page's scope hasn't been refreshed yet this session (shown by the gray **Last trade** badge): both when you switch the toggle on and when you first open such a page. Refreshes run in the background — the page stays fully interactive and updates once with fresh data when each job completes.

### Manual Refresh

Two manual refresh options are available:

| Button | Location | Behaviour |
|---|---|---|
| **Refresh Data** | Top-right of each page | Re-runs smart sync for the current page's symbols (incremental), in the background — the page stays interactive |
| **Force Data Refresh** | Sidebar | Re-fetches quotes and the full date range of daily prices for **every** symbol the app uses — both market research lists plus the holdings of all accounts — ignoring sync state. Company profiles are re-fetched only when older than 7 days. A confirmation dialog shows the unique symbol count first; the job can take a few minutes and blocks the page while running |

On the Portfolio page, "the current page's symbols" means the holdings of **all** your accounts plus the benchmark/header symbols — one refresh keeps every account scope current. Market research pages refresh only their own symbol lists.

Use **Force Data Refresh** when quotes appear stale, after changing the date range significantly, or after adding new symbols to `symbols.yml`.

### Refresh Progress

Background refreshes (the **Refresh Data** button and the **Auto** toggle) show a live progress bar in place of the **Refresh Data** button. The rest of the page stays as it is while the job runs, and redraws once with fresh data when the job finishes.

Blocking refreshes (missing-symbol bootstrap and **Force Data Refresh**) show a progress banner at the top of the page and pause rendering until the job completes. After a Force Data Refresh, every page is marked as refreshed.

Requests to Yahoo Finance are paced (`YF_RATE_LIMIT` in `.env`, default 600 per minute). If Yahoo still answers "Too Many Requests", the refresh pauses for 30 to 120 seconds and retries, so the progress bar can stand still for a while. If some symbols could not be updated when the job ends, a warning names them; refresh again to retry them. If this happens often, lower `YF_RATE_LIMIT`.

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
- **Hide Balances** — use the sidebar toggle to mask monetary values and quantities during screen-sharing; percentage figures stay visible.
- **Hide Account Numbers** — use the sidebar toggle to shorten account numbers to their last two digits and mask the owner name; it works independently of Hide Balances.
- **Multiple accounts** — each account has its own page link in the navigation; click to jump directly between accounts. Each account is independently tracked.
- **Benchmark** — changing the benchmark in the sidebar updates the comparison series on growth charts and performance metrics in real time.
- **symbols.yml** — to add or remove symbols from the market research pages, edit `symbols.yml` in the project root and restart the frontend. No code changes are required. Each group takes a `label` plus an optional `type` (Equity, Fixed Income, Multi-Asset, Commodity, Crypto, Forex, Index) and `region` (US, Canada, International, Global); region nests the Intraday treemap and prefixes the Performance tab's filter options ("US / Core"), and type drives the Intraday type pills. A label can repeat across regions — "Core" can exist under US, Canada and International — since only the region + type + label combination must be unique. Both are optional — groups without them fall back to `Other` and `Global` — and any other value is accepted, sorting after the suggested ones. They are labels only and are never checked against a symbol's exchange or actual holdings.
