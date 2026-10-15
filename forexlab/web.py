"""Local ForexLab dashboard. Start with: python -m forexlab.web"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

import pandas as pd
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import __version__
from .candles import drop_unclosed
from .config import PAIRS, ROOT, TIMEFRAMES, costs_for
from .db import connect, load_backtest_runs, load_candles, load_signals_history, upsert_candles
from .engine import BacktestConfig, run_backtest
from .live_signals import build_live_signals
from .metrics import compute_metrics, equity_curve
from .splits import chronological_split
from .strategies import REGISTRY, parse_params
from .synthetic_data import load_demo_data
from .twelvedata import TwelveDataError, fetch_latest

load_dotenv(ROOT / ".env")
app = FastAPI(title="ForexLab", description="Forex technical analysis & backtesting research desk", version=__version__)


class RefreshRequest(BaseModel):
    symbol: str = "EUR/USD"
    timeframe: str = "1h"


class DemoDataRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: list(PAIRS))
    timeframes: list[str] = Field(default_factory=lambda: list(TIMEFRAMES))
    bars: int = 500


class BacktestRequest(BaseModel):
    symbol: str = "EUR/USD"
    timeframe: str = "1h"
    strategy: str = "ema_cross"
    params: str = ""
    split: str = "train"
    rr: float = 2.0
    risk: float = 1.0
    max_hold: int = 100
    force: bool = False


def _validate_market(symbol, timeframe):
    if symbol not in PAIRS:
        raise HTTPException(status_code=422, detail=f"Unsupported currency pair: {symbol}")
    if timeframe not in TIMEFRAMES:
        raise HTTPException(status_code=422, detail=f"Unsupported timeframe: {timeframe}")


def _clean_json_val(val):
    if isinstance(val, dict):
        return {k: _clean_json_val(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_clean_json_val(v) for v in val]
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
    return val


def _dashboard_data(symbol, timeframe):
    frame = load_candles(symbol, timeframe)
    if frame.empty:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "provider": "Twelve Data",
            "status": "no_data",
            "message": "No candles are stored yet. Add your Twelve Data key and select Refresh, or click 'Load Demo Data'.",
            "candles": [],
            "signals": [],
            "total_candles": 0,
        }

    frame = drop_unclosed(frame, timeframe)
    if frame.empty:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "provider": "Twelve Data",
            "status": "no_closed_candles",
            "message": "Waiting for a candle to close before analysis.",
            "candles": [],
            "signals": [],
            "total_candles": 0,
        }

    candle_close_time = frame.index[-1] + pd.Timedelta(seconds=TIMEFRAMES[timeframe])
    age = max(0, int((pd.Timestamp.now(tz="UTC") - candle_close_time).total_seconds()))
    status = "stale" if age > TIMEFRAMES[timeframe] * 2 else "ready"

    candles = []
    has_vol = "volume" in frame.columns
    for timestamp, row in frame.tail(150).iterrows():
        vol = float(row["volume"]) if has_vol and pd.notna(row["volume"]) else None
        candles.append({
            "time": timestamp.isoformat(),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": vol,
        })

    signals = build_live_signals(frame, symbol, timeframe, persist=True)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "provider": "Twelve Data",
        "status": status,
        "last_closed_candle": frame.index[-1].isoformat(),
        "data_age_seconds": age,
        "last_price": float(frame.iloc[-1]["close"]),
        "total_candles": len(frame),
        "candles": candles,
        "signals": signals,
        "news_status": "not_configured",
        "execution_status": "disabled",
    }


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(Path(__file__).with_name("dashboard.html"))


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": __version__,
        "provider": "Twelve Data",
        "execution": "disabled",
    }


@app.get("/api/markets")
def markets():
    return {
        "pairs": {
            sym: {"pip": meta["pip"], "spread_pips": meta["spread_pips"]}
            for sym, meta in PAIRS.items()
        },
        "timeframes": list(TIMEFRAMES),
        "strategies": list(REGISTRY),
    }


@app.get("/api/dashboard")
def dashboard_data(
    symbol: str = Query("EUR/USD"),
    timeframe: str = Query("1h"),
):
    _validate_market(symbol, timeframe)
    return _dashboard_data(symbol, timeframe)


@app.get("/api/signals/history")
def signals_history(
    symbol: str = Query(None),
    timeframe: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    if symbol and symbol not in PAIRS:
        raise HTTPException(status_code=422, detail=f"Unsupported currency pair: {symbol}")
    if timeframe and timeframe not in TIMEFRAMES:
        raise HTTPException(status_code=422, detail=f"Unsupported timeframe: {timeframe}")
    return load_signals_history(symbol=symbol, timeframe=timeframe, limit=limit)


@app.post("/api/demo-data")
def seed_demo_data(request: DemoDataRequest = DemoDataRequest()):
    for sym in request.symbols:
        if sym not in PAIRS:
            raise HTTPException(status_code=422, detail=f"Unsupported currency pair: {sym}")
    for tf in request.timeframes:
        if tf not in TIMEFRAMES:
            raise HTTPException(status_code=422, detail=f"Unsupported timeframe: {tf}")

    saved = load_demo_data(request.symbols, request.timeframes, n=request.bars)
    default_sym = request.symbols[0] if request.symbols else "EUR/USD"
    default_tf = request.timeframes[0] if request.timeframes else "1h"
    snapshot = _dashboard_data(default_sym, default_tf)
    snapshot["demo_seed"] = {"saved_candles": saved, "completed_at": datetime.now(timezone.utc).isoformat()}
    return snapshot


@app.post("/api/refresh")
def refresh_market(request: RefreshRequest):
    _validate_market(request.symbol, request.timeframe)
    # Reload .env in case user configured it recently
    load_dotenv(ROOT / ".env", override=True)
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise HTTPException(
            status_code=503,
            detail="Set TWELVEDATA_API_KEY in the project .env file before refreshing market data.",
        )

    try:
        frame = fetch_latest(request.symbol, request.timeframe, api_key)
        frame = drop_unclosed(frame, request.timeframe)
        saved = upsert_candles(frame, request.symbol, request.timeframe, "twelvedata")
    except (TwelveDataError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Market data provider error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not retrieve market data from Twelve Data.") from exc

    snapshot = _dashboard_data(request.symbol, request.timeframe)
    snapshot["refresh"] = {"saved_candles": saved, "completed_at": datetime.now(timezone.utc).isoformat()}
    return snapshot


@app.post("/api/backtest")
def run_backtest_endpoint(req: BacktestRequest):
    _validate_market(req.symbol, req.timeframe)
    if req.strategy not in REGISTRY:
        raise HTTPException(status_code=422, detail=f"Unknown strategy: {req.strategy}")
    if req.split not in ("train", "validation", "test"):
        raise HTTPException(status_code=422, detail=f"Invalid split: {req.split}")

    df = load_candles(req.symbol, req.timeframe)
    if df.empty or len(df) < 50:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient candles for {req.symbol} {req.timeframe} (have {len(df)}). Load demo data or fetch history first.",
        )

    try:
        strat_params = parse_params(req.params)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    all_params = {
        "strategy_params": strat_params,
        "rr": req.rr,
        "risk": req.risk,
        "max_hold": req.max_hold,
    }

    # Lock protection for test split
    with connect() as con:
        if req.split == "test":
            prior = con.execute(
                "SELECT COUNT(*) FROM backtest_runs WHERE strategy=? AND symbol=? "
                "AND timeframe=? AND split='test'",
                (req.strategy, req.symbol, req.timeframe),
            ).fetchone()[0]
            if prior and not req.force:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"LOCKED: Test set was already used for {req.strategy} {req.symbol} {req.timeframe}. "
                        "Re-running the test set risks overfitting. Set force=true if accepted."
                    ),
                )

    try:
        signals = REGISTRY[req.strategy](df, **strat_params)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Strategy calculation failed: {exc}")

    parts = chronological_split(df)
    window = parts[req.split]
    if len(window) < 50:
        raise HTTPException(
            status_code=400,
            detail=f"Only {len(window)} candles in {req.split} split. Need more history.",
        )

    spread, slip = costs_for(req.symbol)
    cfg = BacktestConfig(
        rr=req.rr,
        spread=spread,
        slippage=slip,
        max_hold_bars=req.max_hold,
    )
    res = run_backtest(window, signals, cfg)
    years = max((window.index[-1] - window.index[0]).days / 365.25, 1e-9)
    metrics = compute_metrics(res.trades, req.risk, years)

    # Calculate equity curve points
    eq_curve = []
    if len(res.trades) > 0:
        curve_values = equity_curve(res.trades["r"], req.risk)
        eq_curve = [round(float(v), 2) for v in curve_values]
    else:
        eq_curve = [10000.0]

    # Clean metrics for JSON
    cleaned_metrics = _clean_json_val(metrics)

    # Log to backtest_runs
    with connect() as con:
        con.execute(
            "INSERT INTO backtest_runs (created_at, code_version, strategy, symbol, timeframe, "
            "params_json, split, data_start, data_end, n_trades, metrics_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                datetime.now(timezone.utc).isoformat(),
                __version__,
                req.strategy,
                req.symbol,
                req.timeframe,
                json.dumps(all_params, sort_keys=True),
                req.split,
                str(window.index[0]),
                str(window.index[-1]),
                metrics["trades"],
                json.dumps(cleaned_metrics),
            ),
        )

    # Format trades summary
    trade_list = []
    for _, t in res.trades.tail(100).iterrows():
        trade_list.append({
            "entry_ts": str(t["entry_ts"]),
            "exit_ts": str(t["exit_ts"]),
            "direction": "BUY" if t["direction"] == 1 else "SELL",
            "entry": round(float(t["entry"]), 5),
            "exit": round(float(t["exit"]), 5),
            "r": round(float(t["r"]), 3),
            "exit_reason": t["exit_reason"],
            "bars_held": int(t["bars_held"]),
        })

    return {
        "strategy": req.strategy,
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "split": req.split,
        "params": strat_params,
        "window_start": str(window.index[0]),
        "window_end": str(window.index[-1]),
        "candle_count": len(window),
        "skipped_stops": res.skipped.get("stop_too_tight", 0),
        "metrics": cleaned_metrics,
        "equity_curve": eq_curve,
        "trades": trade_list,
    }


@app.get("/api/backtests")
def backtests_list(limit: int = Query(20, ge=1, le=100)):
    return load_backtest_runs(limit=limit)


def main():
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
