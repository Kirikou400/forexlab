"""Closed-candle strategy confluence for the local dashboard."""
from __future__ import annotations

import math

import pandas as pd

from .config import PAIRS
from .indicators import atr
from .strategies import REGISTRY

SCORING_WEIGHTS = {"technical": 0.65, "news": 0.15, "volatility": 0.20}


def confidence_score(technical, volatility, news=None):
    """Return a weighted confluence score, renormalizing unavailable inputs."""
    scores = {"technical": technical, "volatility": volatility}
    if news is not None:
        scores["news"] = news
    weight_total = sum(SCORING_WEIGHTS[name] for name in scores)
    return round(sum(scores[name] * SCORING_WEIGHTS[name] for name in scores) / weight_total)


def _volatility_score(frame):
    values = atr(frame["high"], frame["low"], frame["close"], 14).dropna()
    if len(values) < 10:
        return 50
    baseline = float(values.tail(50).median())
    current = float(values.iloc[-1])
    if baseline <= 0 or current <= 0:
        return 50
    ratio = current / baseline
    return round(max(0, min(100, 100 - abs(math.log(ratio)) * 45)))


def build_live_signals(frame, symbol, timeframe, reward_risk=2.0, persist=True):
    """Analyze the latest closed candle and return any strategy triggers."""
    if frame is None or len(frame) < 2:
        return []

    latest = frame.iloc[-1]
    votes = []
    for name, strategy in REGISTRY.items():
        try:
            result = strategy(frame)
            if result.empty or "direction" not in result or "sl_dist" not in result:
                continue
            direction = int(result["direction"].iloc[-1])
            sl_dist = float(result["sl_dist"].iloc[-1])
            if direction != 0 and math.isfinite(sl_dist) and sl_dist > 0:
                votes.append({
                    "strategy": name,
                    "direction": "BUY" if direction > 0 else "SELL",
                    "direction_value": direction,
                    "stop_distance": sl_dist,
                })
        except Exception:
            continue

    if not votes:
        return []

    volatility = _volatility_score(frame)
    pip = PAIRS.get(symbol, {}).get("pip", 0.0001)
    close = float(latest["close"])
    created_at = frame.index[-1].isoformat()
    signals = []
    for vote in votes:
        direction = vote["direction_value"]
        agreement = sum(item["direction_value"] == direction for item in votes) / len(votes) * 100
        score = confidence_score(agreement, volatility)
        stop_distance = vote["stop_distance"]
        signals.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": vote["strategy"],
            "direction": vote["direction"],
            "confidence": score,
            "score_label": "confluence, not probability",
            "technical_score": round(agreement),
            "volatility_score": volatility,
            "price": close,
            "stop": round(close - direction * stop_distance, 5 if not symbol.endswith("JPY") else 3),
            "target": round(close + direction * stop_distance * reward_risk, 5 if not symbol.endswith("JPY") else 3),
            "stop_pips": round(stop_distance / pip, 1),
            "reasoning": (
                f"{vote['strategy']} triggered on the latest closed candle; "
                f"{agreement:.0f}% of triggered strategies agree."
            ),
            "risk_note": "ATR-based estimates from the candle close; spread, slippage, and execution can change fills.",
            "news_status": "not_configured",
            "news_affected": None,
            "created_at": created_at,
        })
    ranked = sorted(signals, key=lambda item: item["confidence"], reverse=True)
    if persist and ranked:
        try:
            from .db import save_signals
            save_signals(ranked)
        except Exception:
            pass
    return ranked
