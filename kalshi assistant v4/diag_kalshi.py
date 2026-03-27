"""
Diagnostic: prints raw Kalshi 15m WebSocket messages to understand the orderbook format.
"""
import asyncio, json, time, base64, ssl, certifi
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from config import KALSHI_WS_URL, KALSHI_REST_URL, KALSHI_SERIES, KALSHI_API_KEY, KALSHI_PRIVATE_KEY
import requests

def get_active_ticker():
    """Discover the active 15m BTC ticker via REST API v2."""
    path = "/trade-api/v2/markets"
    
    # Sign the request
    private_key = load_pem_private_key(KALSHI_PRIVATE_KEY.encode(), password=None)
    ts = int(time.time() * 1000)
    sig = private_key.sign(
        f"{ts}GET{path}".encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    headers = {
        "KALSHI-ACCESS-KEY": KALSHI_API_KEY,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        "KALSHI-ACCESS-TIMESTAMP": str(ts)
    }
    
    r = requests.get(f"{KALSHI_REST_URL}{path}",
                     params={"limit": 1, "series_ticker": KALSHI_SERIES, "status": "open"},
                     headers=headers)
    print(f"REST Status: {r.status_code}")
    markets = r.json().get("markets", [])
    return markets[0]["ticker"] if markets else None

async def snoop():
    ticker = get_active_ticker()
    print(f"Active ticker: {ticker}")
    if not ticker:
        print("No active markets found. Exiting.")
        return
    
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
    
    ws_url = f"{KALSHI_WS_URL}/trade-api/ws/v2"
    print(f"Connecting to: {ws_url}")
    
    import websockets
    ctx = ssl.create_default_context(cafile=certifi.where())
    async with websockets.connect(ws_url, additional_headers=headers, ssl=ctx) as ws:
        print("Connected!")
        await ws.send(json.dumps({
            "id": 1, "cmd": "subscribe",
            "params": {"channels": ["orderbook_delta"], "market_tickers": [ticker]}
        }))
        # Capture first 5 messages
        for i in range(5):
            msg = await asyncio.wait_for(ws.recv(), timeout=15)
            data = json.loads(msg)
            print(f"\n--- Message {i+1} ---")
            print(json.dumps(data, indent=2))

if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(snoop())
