import asyncio
import json
import base64
import time
import ssl
import certifi
import websockets
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from config import KALSHI_API_KEY, KALSHI_PRIVATE_KEY, KALSHI_WS_URL, KALSHI_REST_URL, KALSHI_SERIES

import requests
async def test_kalshi_ws():
    print(f"WS URL: {KALSHI_WS_URL}/trade-api/ws/v2")
    
    # Get active ticker
    r = requests.get(f"{KALSHI_REST_URL}/trade-api/v2/markets",
                     params={"limit": 1, "series_ticker": KALSHI_SERIES, "status": "open"})
    
    markets = r.json().get("markets", [])
    if not markets:
        print("No open markets found")
        return
    ticker = markets[0]["ticker"]
    print(f"Testing ticker: {ticker}")

    private_key = load_pem_private_key(KALSHI_PRIVATE_KEY.encode(), password=None)
    ts = int(time.time() * 1000)
    sig = private_key.sign(
        f"{ts}GET/trade-api/ws/v2".encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    headers = {
        "KALSHI-ACCESS-KEY": KALSHI_API_KEY,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        "KALSHI-ACCESS-TIMESTAMP": str(ts)
    }
    
    ctx = ssl.create_default_context(cafile=certifi.where())
    async with websockets.connect(f"{KALSHI_WS_URL}/trade-api/ws/v2", additional_headers=headers, ssl=ctx) as ws:
        print(f"Connected! Code: {ws.response.status_code if hasattr(ws, 'response') else 'N/A'}")
        
        # Subscribe to orderbook
        await ws.send(json.dumps({
            "id": 1, "cmd": "subscribe",
            "params": {"channels": ["orderbook_delta"], "market_tickers": [ticker]}
        }))
        print("Subscribed. Waiting for message...")
        msg = await asyncio.wait_for(ws.recv(), timeout=10)
        data = json.loads(msg)
        
        msg2 = await asyncio.wait_for(ws.recv(), timeout=10)
        data2 = json.loads(msg2)
        
        with open("out.json", "w") as f:
            json.dump([data, data2], f, indent=2)
        print("Written to out.json")

if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_kalshi_ws())
