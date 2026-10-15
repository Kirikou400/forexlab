"""Twelve Data client (free tier is fine for the MVP).
Free-tier limits at time of writing: 8 requests/minute, 800/day. Free data
may be delayed and is for non-commercial use: check their current terms.
The candle timestamp returned is the candle OPEN time (we request UTC)."""
import time

import pandas as pd
import requests

API_URL = "https://api.twelvedata.com/time_series"


class TwelveDataError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def parse_time_series(payload: dict) -> pd.DataFrame:
    """Turn one API response into an ascending OHLC DataFrame (UTC index)."""
    if payload.get("status") == "error" or "values" not in payload:
        raise TwelveDataError(payload.get("message", "unexpected response"),
                              payload.get("code"))
    df = pd.DataFrame(payload["values"])
    if df.empty:
        return df
    df.index = pd.to_datetime(df["datetime"], utc=True)
    df.index.name = "ts"
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[cols].apply(pd.to_numeric, errors="raise").sort_index()
    return df[~df.index.duplicated(keep="last")]


def _call(get, params, sleep, max_retries):
    for attempt in range(max_retries + 1):
        payload = get(API_URL, params=params, timeout=30).json()
        if payload.get("code") == 429 and attempt < max_retries:
            print("  rate limit hit, waiting 65s...")
            sleep(65)
            continue
        return payload


def fetch_history(symbol, timeframe, api_key, target_bars,
                  min_interval_s=8.0, max_retries=3, _get=None, _sleep=None):
    """Page backwards in time until we have target_bars candles (or history ends)."""
    get = _get or requests.get
    sleep = _sleep or time.sleep
    frames, have, end_date = [], 0, None
    combined = pd.DataFrame()
    while have < target_bars:
        params = {"symbol": symbol, "interval": timeframe, "outputsize": 5000,
                  "timezone": "UTC", "order": "desc", "apikey": api_key}
        if end_date:
            params["end_date"] = end_date
        payload = _call(get, params, sleep, max_retries)
        try:
            batch = parse_time_series(payload)
        except TwelveDataError as e:
            if frames and e.code != 429:      # ran past the start of history
                print(f"  stopping early: {e}")
                break
            raise
        if batch.empty:
            break
        frames.append(batch)
        combined = pd.concat(frames)
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        if len(combined) == have:
            break
        have = len(combined)
        end_date = (combined.index.min() - pd.Timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {symbol} {timeframe}: {have} candles so far")
        if have < target_bars:
            sleep(min_interval_s)
    return combined


def fetch_latest(symbol, timeframe, api_key, outputsize=500,
                 max_retries=3, _get=None, _sleep=None):
    """Fetch one recent candle batch for an explicit user-triggered refresh."""
    get = _get or requests.get
    sleep = _sleep or time.sleep
    params = {"symbol": symbol, "interval": timeframe, "outputsize": outputsize,
              "timezone": "UTC", "order": "desc", "apikey": api_key}
    payload = _call(get, params, sleep, max_retries)
    return parse_time_series(payload)
