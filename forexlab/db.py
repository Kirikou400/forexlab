"""SQLite storage. SQLite needs no installation, which keeps setup easy for
Step 1. The table layout mirrors the PostgreSQL schema planned for later."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import DB_PATH

TS_FMT = "%Y-%m-%d %H:%M:%S"

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, ts TEXT NOT NULL,
  open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
  volume REAL, source TEXT NOT NULL, fetched_at TEXT NOT NULL,
  PRIMARY KEY (symbol, timeframe, ts)
);
CREATE TABLE IF NOT EXISTS backtest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL, code_version TEXT NOT NULL,
  strategy TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
  params_json TEXT NOT NULL, split TEXT NOT NULL,
  data_start TEXT, data_end TEXT, n_trades INTEGER, metrics_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  detected_at TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  strategy TEXT NOT NULL,
  direction TEXT NOT NULL,
  confidence INTEGER NOT NULL,
  price REAL NOT NULL,
  stop_loss REAL NOT NULL,
  take_profit REAL NOT NULL,
  stop_pips REAL NOT NULL,
  technical_score INTEGER,
  volatility_score INTEGER,
  reasoning TEXT,
  candle_ts TEXT NOT NULL,
  UNIQUE(symbol, timeframe, strategy, candle_ts)
);
"""


@contextmanager
def connect(db_path=None):
    path = Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def upsert_candles(df, symbol, timeframe, source, db_path=None) -> int:
    if df is None or df.empty:
        return 0
    now = datetime.now(timezone.utc).strftime(TS_FMT)
    has_vol = "volume" in df.columns
    rows = []
    for i, ts in enumerate(df.index):
        r = df.iloc[i]
        vol = None
        if has_vol and pd.notna(r["volume"]):
            vol = float(r["volume"])
        rows.append((symbol, timeframe, ts.strftime(TS_FMT),
                     float(r["open"]), float(r["high"]), float(r["low"]),
                     float(r["close"]), vol, source, now))
    with connect(db_path) as con:
        con.executemany(
            "INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def load_candles(symbol, timeframe, db_path=None) -> pd.DataFrame:
    with connect(db_path) as con:
        df = pd.read_sql_query(
            "SELECT ts, open, high, low, close, volume FROM candles "
            "WHERE symbol=? AND timeframe=? ORDER BY ts",
            con, params=(symbol, timeframe))
    if df.empty:
        return df
    df.index = pd.to_datetime(df.pop("ts"), format=TS_FMT, utc=True)
    df.index.name = "ts"
    return df


def list_datasets(db_path=None):
    with connect(db_path) as con:
        return con.execute(
            "SELECT symbol, timeframe, GROUP_CONCAT(DISTINCT source) "
            "FROM candles GROUP BY symbol, timeframe ORDER BY symbol, timeframe"
        ).fetchall()


def save_signals(signals: list, db_path=None) -> int:
    if not signals:
        return 0
    now = datetime.now(timezone.utc).strftime(TS_FMT)
    rows = []
    for s in signals:
        rows.append((
            now,
            s["symbol"],
            s["timeframe"],
            s["strategy"],
            s["direction"],
            int(s.get("confidence", 0)),
            float(s["price"]),
            float(s["stop"]),
            float(s["target"]),
            float(s.get("stop_pips", 0.0)),
            int(s.get("technical_score", 0)),
            int(s.get("volatility_score", 0)),
            s.get("reasoning", ""),
            s.get("created_at", now),
        ))
    with connect(db_path) as con:
        con.executemany(
            "INSERT OR IGNORE INTO signals_history "
            "(detected_at, symbol, timeframe, strategy, direction, confidence, "
            "price, stop_loss, take_profit, stop_pips, technical_score, "
            "volatility_score, reasoning, candle_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def load_signals_history(symbol=None, timeframe=None, limit=50, db_path=None) -> list:
    query = (
        "SELECT id, detected_at, symbol, timeframe, strategy, direction, "
        "confidence, price, stop_loss, take_profit, stop_pips, technical_score, "
        "volatility_score, reasoning, candle_ts FROM signals_history WHERE 1=1"
    )
    params = []
    if symbol:
        query += " AND symbol=?"
        params.append(symbol)
    if timeframe:
        query += " AND timeframe=?"
        params.append(timeframe)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with connect(db_path) as con:
        rows = con.execute(query, params).fetchall()

    return [
        {
            "id": r[0],
            "detected_at": r[1],
            "symbol": r[2],
            "timeframe": r[3],
            "strategy": r[4],
            "direction": r[5],
            "confidence": r[6],
            "price": r[7],
            "stop": r[8],
            "target": r[9],
            "stop_pips": r[10],
            "technical_score": r[11],
            "volatility_score": r[12],
            "reasoning": r[13],
            "candle_ts": r[14],
        }
        for r in rows
    ]


def load_backtest_runs(limit=20, db_path=None) -> list:
    import json
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT id, created_at, code_version, strategy, symbol, timeframe, "
            "params_json, split, data_start, data_end, n_trades, metrics_json "
            "FROM backtest_runs ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r[0],
            "created_at": r[1],
            "code_version": r[2],
            "strategy": r[3],
            "symbol": r[4],
            "timeframe": r[5],
            "params": json.loads(r[6]) if r[6] else {},
            "split": r[7],
            "data_start": r[8],
            "data_end": r[9],
            "n_trades": r[10],
            "metrics": json.loads(r[11]) if r[11] else {},
        })
    return out
