"""Run a backtest on data already stored in the database.

Examples:
  python -m forexlab.run_backtest --symbol EUR/USD --timeframe 1h --strategy ema_cross
  python -m forexlab.run_backtest --strategy donchian --params n=30,atr_mult=2.5 --split validation
  python -m forexlab.run_backtest --strategy ema_cross --split train --walkforward 5
  python -m forexlab.run_backtest --strategy ema_cross --split test      (ONLY ONCE, at the very end)
"""
import argparse
import json
import sys
from datetime import datetime, timezone

from . import __version__
from .config import PAIRS, RESULTS_DIR, TIMEFRAMES, costs_for
from .db import connect, load_candles
from .engine import BacktestConfig, run_backtest
from .metrics import breakdown, compute_metrics, equity_curve, format_report
from .splits import chronological_split, rolling_windows
from .strategies import REGISTRY, parse_params


def _years(df):
    return max((df.index[-1] - df.index[0]).days / 365.25, 1e-9)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None
    return o


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="EUR/USD", choices=list(PAIRS))
    ap.add_argument("--timeframe", default="1h", choices=list(TIMEFRAMES))
    ap.add_argument("--strategy", default="ema_cross", choices=list(REGISTRY))
    ap.add_argument("--params", default="", help="e.g. fast=10,slow=30,atr_mult=2")
    ap.add_argument("--rr", type=float, default=2.0, help="take-profit as multiple of stop distance")
    ap.add_argument("--risk", type=float, default=1.0, help="percent of equity risked per trade")
    ap.add_argument("--max-hold", type=int, default=100, help="max candles to hold a trade")
    ap.add_argument("--split", default="train", choices=["train", "validation", "test"])
    ap.add_argument("--walkforward", type=int, default=0, help="show N consecutive time windows")
    ap.add_argument("--force", action="store_true", help="allow re-running the locked test set (logged)")
    a = ap.parse_args(argv)

    df = load_candles(a.symbol, a.timeframe)
    if df.empty:
        sys.exit(f"No candles for {a.symbol} {a.timeframe}. Run fetch_data or csv_import first.")

    strat_params = parse_params(a.params)
    all_params = {"strategy_params": strat_params, "rr": a.rr, "risk": a.risk, "max_hold": a.max_hold}

    # ---- protect the locked test set -----------------------------------
    with connect() as con:
        if a.split == "test":
            prior = con.execute("SELECT COUNT(*) FROM backtest_runs WHERE strategy=? AND symbol=? "
                                "AND timeframe=? AND split='test'", (a.strategy, a.symbol, a.timeframe)).fetchone()[0]
            if prior and not a.force:
                sys.exit(f"LOCKED: the test set was already used for {a.strategy} {a.symbol} {a.timeframe}. "
                         "Re-running it until it looks good is how overfitting happens. Use --force only "
                         "if you accept that this result is no longer a clean out-of-sample test.")
        tried = con.execute("SELECT COUNT(DISTINCT params_json) FROM backtest_runs WHERE strategy=? AND symbol=? "
                            "AND timeframe=? AND split IN ('train','validation')",
                            (a.strategy, a.symbol, a.timeframe)).fetchone()[0]

    # ---- signals on full history (indicators only look backwards) ------
    signals = REGISTRY[a.strategy](df, **strat_params)
    parts = chronological_split(df)
    window = parts[a.split]
    if len(window) < 200:
        sys.exit(f"Only {len(window)} candles in the {a.split} split: not enough data. Fetch more history.")

    spread, slip = costs_for(a.symbol)
    cfg = BacktestConfig(rr=a.rr, spread=spread, slippage=slip, max_hold_bars=a.max_hold)
    res = run_backtest(window, signals, cfg)
    m = compute_metrics(res.trades, a.risk, _years(window))

    print(f"\n=== {a.strategy} {strat_params or ''} | {a.symbol} {a.timeframe} | split: {a.split} ===")
    print(f"Data: {window.index[0]:%Y-%m-%d} -> {window.index[-1]:%Y-%m-%d}  ({len(window)} candles)")
    print(f"Costs assumed: spread {spread / PAIRS[a.symbol]['pip']:.1f} pips, slippage "
          f"{slip / PAIRS[a.symbol]['pip']:.1f} pips.  Reward:risk target {a.rr}:1, risk {a.risk}% per trade.")
    if res.skipped["stop_too_tight"]:
        print(f"Skipped {res.skipped['stop_too_tight']} signals whose stop was too tight versus costs.")
    print(format_report(m))

    if m["trades"]:
        print("\nBy session (entry time, UTC):\n" + breakdown(res.trades, "session").to_string())
        print("\nBy side:\n" + breakdown(res.trades, "side").to_string())

    if a.walkforward and a.walkforward > 1:
        print(f"\nStability across {a.walkforward} consecutive time windows (same settings):")
        for k, w in enumerate(rolling_windows(window, a.walkforward), 1):
            wr = run_backtest(w, signals, cfg)
            wm = compute_metrics(wr.trades, a.risk, _years(w))
            if wm["trades"]:
                print(f"  window {k}: {w.index[0]:%Y-%m-%d} -> {w.index[-1]:%Y-%m-%d}  "
                      f"trades {wm['trades']:>3}  expectancy {wm['expectancy_r']:+.3f}R  win {wm['win_rate_pct']:.0f}%")
            else:
                print(f"  window {k}: no trades")

    if a.split != "test":
        print(f"\nNOTE: you have tried {tried + 1} distinct setting combination(s) on this strategy/pair/timeframe so far. "
              "The more you try, the more likely the best-looking one is just luck.")
    else:
        print("\nThis was the final out-of-sample test. Do not tune settings based on it.")

    # ---- log the run: every run is stored, good or bad ------------------
    with connect() as con:
        con.execute("INSERT INTO backtest_runs (created_at, code_version, strategy, symbol, timeframe, "
                    "params_json, split, data_start, data_end, n_trades, metrics_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), __version__, a.strategy, a.symbol, a.timeframe,
                     json.dumps(all_params, sort_keys=True), a.split, str(window.index[0]), str(window.index[-1]),
                     m["trades"], json.dumps(_clean(m))))

    RESULTS_DIR.mkdir(exist_ok=True)
    stem = f"{a.strategy}_{a.symbol.replace('/', '')}_{a.timeframe}_{a.split}"
    if m["trades"]:
        res.trades.to_csv(RESULTS_DIR / f"{stem}_trades.csv", index=False)
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            eq = equity_curve(res.trades["r"], a.risk)
            plt.figure(figsize=(9, 4)); plt.plot(eq); plt.title(f"Equity curve: {stem}")
            plt.xlabel("Trade #"); plt.ylabel("Account ($10,000 start)"); plt.grid(alpha=.3)
            plt.tight_layout(); plt.savefig(RESULTS_DIR / f"{stem}_equity.png", dpi=110); plt.close()
        except ImportError:
            pass
        print(f"\nSaved trade list and equity curve in: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
