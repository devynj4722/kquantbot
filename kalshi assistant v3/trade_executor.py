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
import aiohttp
import asyncio
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key


class TradeExecutor:
    def __init__(self, ui_display):
        self.ui = ui_display
        self._private_key = None
        if KALSHI_PRIVATE_KEY:
            self._private_key = load_pem_private_key(KALSHI_PRIVATE_KEY.encode(), password=None)
        self.session = None

    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
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

    async def place_order(self, ticker: str, side: str, yes_price: float) -> dict | None:
        contracts = max(1, int(TRADE_SIZE_DOLLARS / yes_price))
        limit_price = int(round(yes_price * 100))

        if DRY_RUN:
            msg = (f"[DRY RUN] Would place {side.upper()} order: "
                   f"{contracts} contracts @ {limit_price}¢ on {ticker}")
            self.ui.log_info(msg)
            return {"dry_run": True, "ticker": ticker, "side": side,
                    "contracts": contracts, "limit_price": limit_price}

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
                elif r.status in (401, 403):
                    self.ui.log_error("AUTH FAILED — API key may be expired. Check .env.")
                else:
                    text = await r.text()
                    self.ui.log_error(f"Order failed {r.status}: {text[:200]}")
        except Exception as e:
            self.ui.log_error(f"Order exception: {e}")
        return None
