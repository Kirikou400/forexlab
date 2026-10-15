"""Performance statistics. Win rate alone is meaningless: what matters is
expectancy (average R per trade), drawdown, and whether the sample is big
enough to tell skill from luck."""
import math

import numpy as np
import pandas as pd


def wilson_interval(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


def equity_curve(r, risk_pct: float, start: float = 10_000.0) -> np.ndarray:
    """Compounded account balance risking risk_pct of equity per trade."""
    mult = np.clip(1 + risk_pct / 100.0 * np.asarray(r, float), 0, None)
    return start * np.concatenate([[1.0], np.cumprod(mult)])


def longest_losing_streak(r) -> int:
    best = cur = 0
    for x in r:
        cur = cur + 1 if x <= 0 else 0
        best = max(best, cur)
    return best


def session_of(hour: int) -> str:
    if 0 <= hour < 7: return "Asia"
    if 7 <= hour < 12: return "London"
    if 12 <= hour < 16: return "London/NY overlap"
    if 16 <= hour < 21: return "New York"
    return "Late/rollover"


def compute_metrics(trades: pd.DataFrame, risk_pct: float, years: float, start: float = 10_000.0) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "warnings": ["No trades were generated."]}
    r = trades["r"].to_numpy(float)
    wins, losses = r[r > 0], r[r <= 0]
    eq = equity_curve(r, risk_pct, start)
    dd = eq / np.maximum.accumulate(eq) - 1
    mean, sd = r.mean(), r.std(ddof=1) if n > 1 else float("nan")
    se = sd / math.sqrt(n) if n > 1 else float("nan")
    lo, hi = wilson_interval(len(wins), n)
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = losses.mean() if len(losses) else 0.0
    tpy = n / years if years > 0 else float("nan")
    m = {
        "trades": n, "wins": int(len(wins)), "losses": int(len(losses)),
        "win_rate_pct": 100 * len(wins) / n,
        "win_rate_ci95_pct": (100 * lo, 100 * hi),
        "avg_win_r": float(avg_win), "avg_loss_r": float(avg_loss),
        "breakeven_win_rate_pct": (100 / (1 + avg_win / abs(avg_loss))) if avg_win and avg_loss else None,
        "expectancy_r": float(mean),
        "expectancy_ci95_r": (float(mean - 1.96 * se), float(mean + 1.96 * se)) if n > 1 else (None, None),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else None,
        "net_return_pct": float((eq[-1] / eq[0] - 1) * 100),
        "max_drawdown_pct": float(-dd.min() * 100),
        "longest_losing_streak": longest_losing_streak(r),
        "sharpe_annualised_approx": float(mean / sd * math.sqrt(tpy)) if sd and sd > 0 and tpy == tpy else None,
        "trades_per_year": float(tpy),
        "exit_reasons": trades["exit_reason"].value_counts().to_dict(),
        "warnings": [],
    }
    if n < 100:
        m["warnings"].append(f"Only {n} trades: too few to trust. Treat as anecdote, not evidence.")
    lo_e, hi_e = m["expectancy_ci95_r"]
    if lo_e is not None and lo_e <= 0 <= hi_e:
        m["warnings"].append("Expectancy is statistically indistinguishable from zero (95% interval spans 0).")
    return m


def breakdown(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    t = trades.copy()
    if by == "session":
        t["session"] = t["entry_ts"].dt.hour.map(session_of)
    elif by == "side":
        t["side"] = np.where(t["direction"] == 1, "BUY", "SELL")
    g = t.groupby(by)["r"]
    return pd.DataFrame({"trades": g.size(), "win_rate_pct": g.apply(lambda x: 100 * (x > 0).mean()),
                         "expectancy_r": g.mean()}).round(3)


def format_report(m: dict) -> str:
    if m["trades"] == 0:
        return "No trades. " + " ".join(m["warnings"])
    f = lambda v, s="": "n/a" if v is None else f"{v:.2f}{s}"
    lo, hi = m["win_rate_ci95_pct"]
    elo, ehi = m["expectancy_ci95_r"]
    lines = [
        f"Trades: {m['trades']}  (wins {m['wins']}, losses {m['losses']})",
        f"Win rate: {m['win_rate_pct']:.1f}%   95% range {lo:.1f}-{hi:.1f}%   "
        f"(break-even at this payoff: {f(m['breakeven_win_rate_pct'], '%')})",
        f"Avg win: {m['avg_win_r']:.2f}R   Avg loss: {m['avg_loss_r']:.2f}R",
        f"Expectancy: {m['expectancy_r']:+.3f}R per trade   95% range {f(elo)} to {f(ehi)}",
        f"Profit factor: {f(m['profit_factor'])}   Net return: {m['net_return_pct']:+.1f}%   "
        f"Max drawdown: {m['max_drawdown_pct']:.1f}%",
        f"Longest losing streak: {m['longest_losing_streak']}   Sharpe (approx): {f(m['sharpe_annualised_approx'])}",
        f"Exits: {m['exit_reasons']}",
    ]
    lines += [f"!! {w}" for w in m["warnings"]]
    return "\n".join(lines)
