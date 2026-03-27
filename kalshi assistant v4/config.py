# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# ── Load both key pairs from .env ─────────────────────────────────────────────
_strip_key = lambda k: k.strip().strip('"').strip("'").replace("\\n", "\n")

KALSHI_PROD_API_KEY = os.getenv("KALSHI_PROD_API_KEY", "").strip()
KALSHI_PROD_PRIVATE_KEY = _strip_key(os.getenv("KALSHI_PROD_PRIVATE_KEY", ""))

KALSHI_DEMO_API_KEY = os.getenv("KALSHI_DEMO_API_KEY", "").strip()
KALSHI_DEMO_PRIVATE_KEY = _strip_key(os.getenv("KALSHI_DEMO_PRIVATE_KEY", ""))

# Kalshi Configuration
USE_DEMO = False           # Set to False to trade on Production (Real Money)
DRY_RUN = False            # Set to False to ALLOW the bot to place orders on Kalshi

if USE_DEMO:
    KALSHI_API_KEY = KALSHI_DEMO_API_KEY
    KALSHI_PRIVATE_KEY = KALSHI_DEMO_PRIVATE_KEY
    KALSHI_REST_URL = "https://demo-api.kalshi.co"
    KALSHI_WS_URL = "wss://demo-api.kalshi.co"
else:
    KALSHI_API_KEY = KALSHI_PROD_API_KEY
    KALSHI_PRIVATE_KEY = KALSHI_PROD_PRIVATE_KEY
    KALSHI_REST_URL = "https://api.elections.kalshi.com"
    KALSHI_WS_URL = "wss://api.elections.kalshi.com"

# 15-minute BTC up/down markets — auto-discovers the current active ticker
KALSHI_SERIES = "KXBTC15M"

# Coinbase Configuration
COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
COINBASE_PRODUCT_ID = "BTC-USD"
COINBASE_REST_URL = "https://api.exchange.coinbase.com"  # Public REST for candle seeding

# Statistical Thresholds
ATR_PERIODS = 15          # Rolling 15-minute Average True Range
Z_SCORE_THRESHOLD = 2.0
EV_THRESHOLD = 0.02   # Lowered for binary markets with sigmoid p_win model
RSI_OB_THRESHOLD = 70  # Tuned for 15m binary (standard swing thresholds)
RSI_OS_THRESHOLD = 30  # Tuned for 15m binary (standard swing thresholds)
RSI_SIGNAL_UP = 45   # Threshold for Bullish Bias
RSI_SIGNAL_DOWN = 55 # Threshold for Bearish Bias
ATR_DIST_KILL_SWITCH = 2.0
OI_PCT_THRESHOLD = 0.015  # 1.5%

# Analysis Windows (Snapshots per Window)
OI_15M_SAMPLES = 30     # 15m / 30s
PRICE_15M_SAMPLES = 900 # 15m / 1s

# Market Microstructure
MIN_WALL_VOLUME = 1.0   # Shows all liquidity walls (for testing/verification)
ORDERBOOK_PRICE_BUCKET_SIZE = 0.01 # 1 cent resolution for contracts (0.01 scale)

# ── Trading Settings ──────────────────────────────────────────────────────────
# DRY_RUN is now managed at the top under Kalshi Configuration
TRADE_SIZE_DOLLARS = 5   # Max dollars to risk per Prime Setup signal
MAX_OPEN_POSITIONS = 3    # Don't fire more than this many unresolved signals per session
