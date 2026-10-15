# ForexLab: Forex Analysis and Backtesting

ForexLab is a local research app for forex candles, technical strategy analysis, and honest backtesting. Its browser dashboard ranks setups from completed candles; its backtester tests whether a rule held up after costs on data it had not seen.

The dashboard is analysis-only. It does not place orders. A displayed confluence score is a heuristic, not a probability of profit or a promise of performance. Nothing here is financial advice.

## EASIEST WAY (no typing commands)
1. Install Python from https://www.python.org/downloads/ and tick **"Add python.exe to PATH"**.
2. Unzip this folder. Double-click **setup.bat** (once). Wait for "OK".
3. Double-click **ForexLab.bat**.
   - Option 3 loads demo candles immediately without needing an API key.
   - Option 2 opens the browser dashboard & strategy backtester at http://127.0.0.1:8000.
The rest of this file is the manual version for reference.

## 1. One-time setup on Windows

1. **Install Python** from https://www.python.org/downloads/ (get 3.12 or newer).
   On the first installer screen, **tick "Add python.exe to PATH"**, then Install.
2. **Install VS Code** (https://code.visualstudio.com) and open this folder with *File > Open Folder*.
3. Open a terminal in VS Code (*Terminal > New Terminal*, choose **Command Prompt** from the dropdown, which avoids PowerShell permission issues) and run:

```
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
You should now see `(.venv)` at the start of the line. Do `.venv\Scripts\activate` again whenever you open a new terminal.

4. **Check everything works** (no internet or data needed):
```
python -m unittest discover -s tests -t .
```
You should see all 40 tests pass with `OK`.

5. **Start the browser dashboard:**
```
python -m forexlab.web
```
Open http://127.0.0.1:8000. Choose a pair and timeframe. If you don't have an API key yet, click **"Load Demo Data"** to populate realistic market candles instantly.
If you have a Twelve Data key in `.env`, click **"Refresh market data"**. After a successful refresh, the app polls once per minute while open.

## 2. Get data (choose A, B, or C)

**A. Demo Market Data (instant, no key needed).**
```
python -m forexlab.demo_data
```
Populates EUR/USD, GBP/USD, USD/JPY, and AUD/USD with realistic multi-timeframe candles (15min, 1h, 4h) for offline testing, strategy exploration, and backtesting.

**B. Twelve Data (live API).** Create an account at https://twelvedata.com and copy your API key
into the `.env` file. The dashboard fetches recent candles when you refresh; to preload deeper history, run:
```
python -m forexlab.fetch_data
```
Free tier limits (8 requests/min, 800/day) mean this takes several minutes; it waits automatically.

**C. CSV files (deepest history, free).** Download 1-minute or hourly candles (e.g. from Dukascopy), then:
```
python -m forexlab.csv_import path\to\eurusd_1m.csv --symbol EUR/USD --file-timeframe 1min --source dukascopy
```
Times must be UTC. Use one source per pair/timeframe; do not mix.

**Always run the data check before trusting any result:**
```
python -m forexlab.check_data
```

## 3. Run a backtest

```
python -m forexlab.run_backtest --symbol EUR/USD --timeframe 1h --strategy ema_cross
python -m forexlab.run_backtest --strategy donchian --params n=30,atr_mult=2.5 --split validation
python -m forexlab.run_backtest --strategy ema_cross --split train --walkforward 5
```
Options: `--rr 2` (target = 2x stop), `--risk 1` (% per trade), `--max-hold 100`.
Results (trade list CSV + equity-curve PNG) are saved in `results\`.

### The workflow that keeps you honest
| Split | Data | Purpose |
|---|---|---|
| train | first 50% | explore |
| validation | next 25% | compare settings |
| test | last 25% | **LOCKED**: run once, at the very end |

The program counts how many settings you've tried (more tries = more chance the "best" is luck) and
**refuses to run the test set twice** for the same strategy/pair/timeframe.

### How to read the output
- **Expectancy (R)** is the average result per trade in units of risk. Positive after costs is required. Win rate alone means nothing.
- **95% range** next to it: if it spans zero, you cannot tell the strategy from luck.
- **Trades < 100**: treat as anecdote.
- **Stability windows**: an edge that exists in only one window is probably not an edge.
- Tip: split results by session/side on small samples always show "winners" even in random data. Don't chase them.

## 4. What the engine guarantees (each is unit-tested)
- Signals at candle close are filled at the **next** candle's open (never at the price that triggered them).
- Spread + slippage are charged on every trade; unfilled-order optimism is avoided.
- If stop and target both fall inside one candle, the **stop** is assumed to hit first.
- Gaps through a stop fill at the gap price, not the stop.
- Indicators and signals use no future data (tests remove the future and confirm results don't change).
- A random-walk (no-edge) dataset must not show profit (tests confirm).
- Unfinished (still-forming) candles are dropped on download.

## 5. Known limitations (be aware)
- Fixed assumed spreads in `forexlab/config.py`; **replace with your broker's real numbers**. Real spreads widen at news/rollover.
- Mid-price candles; no swap/financing; one trade at a time; no news filter yet.
- SQLite for now (no install needed); the schema matches the planned PostgreSQL design.
- Timezone/session boundaries (e.g. how 4h candles align) depend on the data source.
- Market data currently comes from Twelve Data's candle REST API, not a tick stream or TradingView API. Refresh is polled no faster than once a minute after the first successful manual refresh; actual freshness depends on your provider plan.
- The dashboard currently runs locally without user accounts. News/calendar scoring, push delivery, PostgreSQL/TimescaleDB, machine learning, and broker execution are not implemented. Order execution is intentionally disabled.
- The position-size estimate assumes your account currency is the pair's quote currency. It is not broker-aware and should not be used as an order instruction.

## 6. Current signal modules & Web Terminal
- `ema_cross`, `sma_cross`, `macd_cross`, `rsi_reversal`, and `donchian` share one strategy registry with the backtester.
- **Signal Desk**: Live confluence scoring across all 5 strategies on the latest closed candle.
- **Interactive Candlestick Chart**: Toggle between realistic candlesticks and line charts with Entry, Stop Loss, and Take Profit levels overlaid upon selecting any setup.
- **Integrated Strategy Backtester**: Run train/validation/test backtests directly inside the web UI, view compounded equity curves on canvas, and inspect detailed trade logs.
- **Signal Log**: Automatic audit trail and historical persistence of triggered setups in SQLite.
- **Position Size Sizer**: Dynamically calculates position size (units, standard/mini lots, and monetary risk) based on account balance and stop loss distance.

## 7. Layout
```
forexlab/  config.py  db.py  candles.py  twelvedata.py  fetch_data.py  synthetic_data.py
           demo_data.py  csv_import.py  quality.py  check_data.py  indicators.py
           strategies.py  live_signals.py  engine.py  metrics.py  splits.py
           run_backtest.py  web.py  dashboard.html
tests/     engine, no-lookahead, no-edge-in-noise, data-layer, signal tests, web API tests
```
