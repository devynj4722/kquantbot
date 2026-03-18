# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# Kalshi Credentials
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY", "").strip()
# Handle potential quotes and literal newlines in .env
KALSHI_PRIVATE_KEY = os.getenv("KALSHI_PRIVATE_KEY", "").strip().strip('"').strip("'").replace("\\n", "\n")

# Kalshi Configuration
USE_DEMO = False          # Set to False to trade on Production (Real Money)
DRY_RUN = False            # Set to False to ALLOW the bot to place orders on Kalshi

if USE_DEMO:
    KALSHI_REST_URL = "https://demo.kalshi.co"
    KALSHI_WS_URL = "wss://demo.kalshi.co"
else:
    # Use elections endpoint as it's the modern high-performance one
    KALSHI_REST_URL = "https://api.elections.kalshi.com"
    KALSHI_WS_URL = "wss://api.elections.kalshi.com"

# 15-minute BTC up/down markets — auto-discovers the current active ticker
KALSHI_SERIES = "KXBTC15M"

# Coinbase Configuration
COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
COINBASE_PRODUCT_ID = "BTC-USD"
COINBASE_REST_URL = "https://api.exchange.coinbase.com"  # Public REST for candle seeding

# Math Engine Thresholds
ATR_PERIODS = 15          # Rolling 15-minute Average True Range
Z_SCORE_THRESHOLD = 2.0   # Z-Score extremeness threshold
EV_THRESHOLD = 0.0        # Expected value must be strictly > 0

# Orderbook Parameters
ORDERBOOK_PRICE_BUCKET_SIZE = 0.01  # Increased resolution for walls
MIN_WALL_VOLUME = 200            # Lowered threshold to see more activity

# ── Trading Settings ──────────────────────────────────────────────────────────
# DRY_RUN is now managed at the top under Kalshi Configuration
TRADE_SIZE_DOLLARS = 5   # Max dollars to risk per Prime Setup signal
MAX_OPEN_POSITIONS = 3    # Don't fire more than this many unresolved signals per session
