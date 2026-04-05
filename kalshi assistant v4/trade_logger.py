"""
trade_logger.py
Logs Prime Setup events and trade outcomes to trades.csv.
Supports outcome reconciliation after market settlement.
"""
import csv
import os
import time
from datetime import datetime, timezone

TRADES_CSV = os.path.join(os.path.dirname(__file__), "trades.csv")

FIELDNAMES = [
    "timestamp", "ticker", "direction", "ev", "edge_cents", "z_score", "rsi",
    "macd_histogram", "market_p_win", "yes_price", "kci", "composite_score",
    "setup_type", "size_dollars", "dry_run", "outcome", "pnl_est"
]


def _ensure_header():
    """Creates the CSV with current headers, or migrates an existing file."""
    if not os.path.exists(TRADES_CSV) or os.path.getsize(TRADES_CSV) == 0:
        with open(TRADES_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
        return

    # Migrate: if file exists but header is outdated, rewrite with new columns
    with open(TRADES_CSV, "r", newline="") as f:
        reader = csv.DictReader(f)
        existing_fields = reader.fieldnames or []
        if set(existing_fields) == set(FIELDNAMES):
            return  # Header is up-to-date
        rows = list(reader)

    # Rewrite with new header; old rows get "" for missing fields
    with open(TRADES_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean = {k: row.get(k, "") for k in FIELDNAMES}
            writer.writerow(clean)


def log_signal(ticker: str, direction: str, ev: float, edge_cents: float,
               z_score: float, rsi: float, macd_histogram: float,
               market_p_win: float, yes_price: float, kci: float,
               composite_score: float, setup_type: str,
               size_dollars: float, dry_run: bool) -> str:
    """
    Logs a trade signal with full context. Returns timestamp as signal_id.
    """
    _ensure_header()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "timestamp": ts,
        "ticker": ticker,
        "direction": direction,
        "ev": round(ev, 4),
        "edge_cents": round(edge_cents, 1),
        "z_score": round(z_score, 4),
        "rsi": round(rsi, 2),
        "macd_histogram": round(macd_histogram, 6),
        "market_p_win": round(market_p_win, 4),
        "yes_price": round(yes_price, 4),
        "kci": round(kci, 1),
        "composite_score": round(composite_score, 1),
        "setup_type": setup_type,
        "size_dollars": round(size_dollars, 2),
        "dry_run": dry_run,
        "outcome": "PENDING",
        "pnl_est": ""
    }
    with open(TRADES_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(row)
    return ts


def get_pending_tickers() -> list[str]:
    """Returns a list of unique tickers that still have outcome == PENDING."""
    if not os.path.exists(TRADES_CSV):
        return []
    with open(TRADES_CSV, "r", newline="") as f:
        rows = list(csv.DictReader(f))
    seen = set()
    tickers = []
    for row in rows:
        ticker = row.get("ticker", "")
        if row.get("outcome", "") == "PENDING" and ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tickers


def update_outcome(ticker: str, outcome: str, pnl_est: float = 0.0) -> int:
    """
    Updates all PENDING rows matching `ticker` with the given outcome and P&L.
    Returns the number of rows updated.

    outcome should be one of: "WIN", "LOSS", "PUSH" (if settled at entry price).
    pnl_est is the estimated profit/loss in dollars (positive = profit).
    """
    if not os.path.exists(TRADES_CSV):
        return 0

    with open(TRADES_CSV, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    updated = 0
    for row in rows:
        if row.get("ticker") == ticker and row.get("outcome") == "PENDING":
            row["outcome"] = outcome
            row["pnl_est"] = round(pnl_est, 4)
            updated += 1

    if updated > 0:
        with open(TRADES_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

    return updated


def get_performance_summary() -> dict:
    """
    Returns a summary of trading performance from trades.csv.
    Useful for quick P&L review.
    """
    if not os.path.exists(TRADES_CSV):
        return {"total": 0, "wins": 0, "losses": 0, "pending": 0,
                "win_rate": 0.0, "total_pnl": 0.0}

    with open(TRADES_CSV, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    wins = sum(1 for r in rows if r.get("outcome") == "WIN")
    losses = sum(1 for r in rows if r.get("outcome") == "LOSS")
    pending = sum(1 for r in rows if r.get("outcome") == "PENDING")
    total_pnl = 0.0
    for r in rows:
        try:
            pnl = float(r.get("pnl_est", 0) or 0)
            total_pnl += pnl
        except (ValueError, TypeError):
            pass

    resolved = wins + losses
    win_rate = (wins / resolved * 100) if resolved > 0 else 0.0

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2)
    }


def get_pending_positions() -> list[dict]:
    """Returns all PENDING rows as dicts. Used by portfolio hedging."""
    if not os.path.exists(TRADES_CSV):
        return []
    with open(TRADES_CSV, "r", newline="") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r.get("outcome") == "PENDING"]


def get_last_signal() -> dict | None:
    """Returns the most recent row from trades.csv as a dict, or None."""
    if not os.path.exists(TRADES_CSV):
        return None
    with open(TRADES_CSV, "r", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else None
