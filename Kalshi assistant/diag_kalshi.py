"""
Diagnostic: prints raw Kalshi 15m WebSocket messages to understand the orderbook format.
"""
import asyncio, json, time, base64, requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from config import KALSHI_WS_URL, KALSHI_REST_URL, KALSHI_SERIES, KALSHI_API_KEY, KALSHI_PRIVATE_KEY

def get_active_ticker():
    r = requests.get(f"{KALSHI_REST_URL}/markets",
                     params={"limit": 1, "series_ticker": KALSHI_SERIES, "status": "open"})
    markets = r.json().get("markets", [])
    return markets[0]["ticker"] if markets else None

async def snoop():
    ticker = get_active_ticker()
    print(f"Active ticker: {ticker}")
    
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
    
    import websockets
    async with websockets.connect(KALSHI_WS_URL, additional_headers=headers) as ws:
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
