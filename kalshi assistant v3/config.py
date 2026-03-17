# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# Kalshi Credentials
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY", "")
KALSHI_PRIVATE_KEY = os.getenv("KALSHI_PRIVATE_KEY", "").replace("\\n", "\n")

# Kalshi Configuration
KALSHI_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
KALSHI_REST_URL = "https://api.elections.kalshi.com/trade-api/v2"

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
ORDERBOOK_PRICE_BUCKET_SIZE = 0.05
MIN_WALL_VOLUME = 500

# ── Trading Settings ──────────────────────────────────────────────────────────
DRY_RUN = True            # True = log only, False = place real orders on Kalshi
TRADE_SIZE_DOLLARS = 10   # Max dollars to risk per Prime Setup signal
MAX_OPEN_POSITIONS = 3    # Don't fire more than this many unresolved signals per session
