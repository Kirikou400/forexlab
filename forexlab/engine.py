"""Backtest engine: honest fills, no look-ahead.

Rules (each one exists to stop results from being inflated):
 1. A signal decided at the CLOSE of bar t is filled at the OPEN of bar t+1.
 2. Prices are treated as MID prices. We pay half the spread on entry and
    on exit, plus adverse slippage on entries and on stop-loss exits.
    Buys fill at the ask (mid + half spread); sells at the bid (mid - half).
 3. Stop/target levels are set from the intended (mid) entry price.
    Risk is 1R = stop distance. Costs are charged on top, so a stopped trade
    loses slightly MORE than -1R and a winner earns slightly LESS than +rr.
 4. If stop and target are both touched inside one candle we assume the
    STOP was hit first (we can't know the order; assume the worst).
 5. If a candle opens beyond a stop, we fill at that open (gap), not the stop.
 6. One trade at a time. Trades are force-closed after max_hold_bars, and at
    the end of the data window.
 7. Stops smaller than min_sl_to_cost x (spread + slippage) are skipped:
    when costs eat the stop, results are meaningless.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestConfig:
    rr: float = 2.0             # take-profit distance as a multiple of stop distance
    spread: float = 0.0         # FULL spread, price units
    slippage: float = 0.0       # price units
    max_hold_bars: int = 100
    min_sl_to_cost: float = 3.0


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    skipped: dict
    n_bars: int


def run_backtest(df: pd.DataFrame, signals: pd.DataFrame, cfg: BacktestConfig) -> BacktestResult:
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    direction = signals["direction"].reindex(df.index).fillna(0).to_numpy()
    sl_dists = signals["sl_dist"].reindex(df.index).to_numpy(float)
    idx, n = df.index, len(df)
    half, slip = cfg.spread / 2.0, cfg.slippage
    skipped = {"stop_too_tight": 0}
    trades = []

    i = 0
    while i < n - 1:
        d = int(direction[i])
        sl_dist = sl_dists[i]
        if d == 0 or not np.isfinite(sl_dist) or sl_dist <= 0:
            i += 1
            continue
        if cfg.spread + slip > 0 and sl_dist < cfg.min_sl_to_cost * (cfg.spread + slip):
            skipped["stop_too_tight"] += 1
            i += 1
            continue

        e = i + 1                                   # fill bar
        mid_entry = o[e]
        entry_fill = mid_entry + d * (half + slip)  # buy at ask / sell at bid, plus slippage
        sl = mid_entry - d * sl_dist
        tp = mid_entry + d * cfg.rr * sl_dist

        # Work in "direction space": x = d * price, so "down" is always bad for us.
        # Exit-side price is the bid for longs (mid - half) and the ask for shorts (mid + half).
        adj = -d * half
        sl_x, tp_x = d * sl, d * tp
        last_j = min(n - 1, e + cfg.max_hold_bars - 1)
        exit_x, reason = None, None
        for j in range(e, last_j + 1):
            p_open, p_high, p_low = o[j] + adj, h[j] + adj, l[j] + adj
            x_open = d * p_open
            x_worst, x_best = (p_low, p_high) if d == 1 else (-p_high, -p_low)
            if x_open <= sl_x:                       # gapped through the stop
                exit_x, reason = x_open, "sl"; break
            if x_open >= tp_x:                       # gapped through the target
                exit_x, reason = x_open, "tp"; break
            if x_worst <= sl_x:                      # stop checked BEFORE target (worst case)
                exit_x, reason = sl_x - slip, "sl"; break
            if x_best >= tp_x:
                exit_x, reason = tp_x, "tp"; break
        else:
            j = last_j
            exit_x = d * (c[j] + adj)
            reason = "time" if last_j == e + cfg.max_hold_bars - 1 else "end_of_data"

        r = (exit_x - d * entry_fill) / sl_dist
        trades.append({"signal_ts": idx[i], "entry_ts": idx[e], "exit_ts": idx[j],
                       "direction": d, "entry": entry_fill, "exit": d * exit_x,
                       "sl": sl, "tp": tp, "sl_dist": sl_dist, "r": r,
                       "exit_reason": reason, "bars_held": j - e + 1})
        i = j        # a new signal at the close of the exit bar may enter at the next open

    cols = ["signal_ts", "entry_ts", "exit_ts", "direction", "entry", "exit",
            "sl", "tp", "sl_dist", "r", "exit_reason", "bars_held"]
    return BacktestResult(pd.DataFrame(trades, columns=cols), skipped, n)
