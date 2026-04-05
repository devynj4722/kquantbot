"""
trade_executor.py
Places YES/NO orders on the Kalshi REST API.
DRY_RUN mode (default True) logs the intent without placing a real order.
"""
import base64
import time
import json
import requests
from config import KALSHI_API_KEY, KALSHI_PRIVATE_KEY, KALSHI_REST_URL, DRY_RUN, TRADE_SIZE_DOLLARS
import asyncio
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

# aiohttp is only needed if DRY_RUN=False (live trading)
try:
    import aiohttp
except ImportError:
    aiohttp = None


class TradeExecutor:
    def __init__(self, ui_display):
        self.ui = ui_display
        self._private_key = None
        if KALSHI_PRIVATE_KEY:
            self._private_key = load_pem_private_key(KALSHI_PRIVATE_KEY.encode(), password=None)
        self.session = None

    async def get_session(self):
        if aiohttp is None:
            raise RuntimeError("aiohttp is required for live trading (DRY_RUN=False). Install with: pip install aiohttp")

        if self.session is None or self.session.closed:
            import ssl
            import certifi
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            # Browser-grade headers to avoid Cloudflare/Akamai detection
            host = KALSHI_REST_URL.split("://")[1]
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": f"{KALSHI_REST_URL}/",
                "Origin": KALSHI_REST_URL,
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin"
            }
            self.session = aiohttp.ClientSession(connector=connector, headers=headers)
        return self.session

    def _sign_rest(self, method: str, path: str) -> dict:
        ts = int(time.time() * 1000)
        msg = f"{ts}{method}{path}"
        sig = self._private_key.sign(
            msg.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return {
            "KALSHI-ACCESS-KEY": KALSHI_API_KEY,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": str(ts),
            "Content-Type": "application/json"
        }

    async def place_order(self, ticker: str, side: str, yes_price: float,
                          size_dollars: float = 1.0,
                          composite_score: float = 0.0,
                          setup_type: str = "") -> dict | None:
        """
        Places a limit order on Kalshi.  Size is pre-computed by EdgeEngine.
        Kalshi binary contracts require yes_price in range 1-99 cents.
        """
        # Clamp to valid Kalshi price range (1-99 cents)
        limit_price = max(1, min(99, int(round(yes_price * 100))))

        # Reject obviously bad prices (near 0% or 100% probability)
        if yes_price <= 0.02 or yes_price >= 0.98:
            self.ui.log_error(
                f"Price sanity check failed: {yes_price:.4f} "
                f"({limit_price}¢) — too close to 0/100. Skipping order.")
            return None

        contracts = max(1, int(size_dollars / max(yes_price, 0.01)))

        if DRY_RUN:
            msg = (f"[DRY RUN] {side.upper()} {contracts}x @ {limit_price}¢ on {ticker} | "
                   f"${size_dollars:.2f} risk | Score {composite_score:.1f} | {setup_type}")
            self.ui.log_info(msg)
            return {"dry_run": True, "ticker": ticker, "side": side,
                    "contracts": contracts, "limit_price": limit_price,
                    "size_dollars": size_dollars, "composite_score": composite_score,
                    "setup_type": setup_type}

        path = "/trade-api/v2/portfolio/orders"
        headers = self._sign_rest("POST", path)
        body = {
            "ticker": ticker,
            "client_order_id": f"kalshibot_{int(time.time())}",
            "type": "limit",
            "action": "buy",
            "side": side,
            "count": contracts,
            "yes_price": limit_price
        }
        
        try:
            session = await self.get_session()
            async with session.post(f"{KALSHI_REST_URL}{path}", headers=headers,
                                     json=body, timeout=10) as r:
                if r.status in (200, 201):
                    res = await r.json()
                    self.ui.log_info(f"Order placed: {side.upper()} {contracts}x {ticker} @ {limit_price}¢")
                    return res
                elif r.status == 429:
                    self.ui.log_error("KALSHI RATE LIMIT (429) — Order might have been throttled.")
                elif r.status in (401, 403):
                    self.ui.log_error("AUTH FAILED — API key may be expired. Check .env.")
                else:
                    text = await r.text()
                    self.ui.log_error(f"Order failed {r.status}: {text[:200]}")
        except Exception as e:
            self.ui.log_error(f"Order exception: {e}")
        return None
