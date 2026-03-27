"""
trade_logger.py
Logs Prime Setup events and trade outcomes to trades.csv.
"""
import csv
import os
import time
from datetime import datetime, timezone

TRADES_CSV = os.path.join(os.path.dirname(__file__), "trades.csv")

FIELDNAMES = [
    "timestamp", "ticker", "direction", "ev", "z_score", "rsi",
    "macd_histogram", "market_p_win", "yes_price", "kci", "dry_run",
    "outcome", "pnl_est"
]


def _ensure_header():
    if not os.path.exists(TRADES_CSV) or os.path.getsize(TRADES_CSV) == 0:
        with open(TRADES_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def log_signal(ticker: str, direction: str, ev: float, z_score: float,
               rsi: float, macd_histogram: float, market_p_win: float,
               yes_price: float, kci: float, dry_run: bool) -> str:
    """
    Logs a Prime Setup signal. Returns a unique signal_id (timestamp string)
    so the caller can later update the outcome.
    """
    _ensure_header()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "timestamp": ts,
        "ticker": ticker,
        "direction": direction,
        "ev": round(ev, 4),
        "z_score": round(z_score, 4),
        "rsi": round(rsi, 2),
        "macd_histogram": round(macd_histogram, 6),
        "market_p_win": round(market_p_win, 4),
        "yes_price": round(yes_price, 4),
        "kci": round(kci, 1),
        "dry_run": dry_run,
        "outcome": "PENDING",
        "pnl_est": ""
    }
    with open(TRADES_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(row)
    return ts


def get_last_signal() -> dict | None:
    """Returns the most recent row from trades.csv as a dict, or None."""
    if not os.path.exists(TRADES_CSV):
        return None
    with open(TRADES_CSV, "r", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else None
