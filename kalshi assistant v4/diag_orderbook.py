"""
Diagnostic: connect to Kalshi WS and inspect raw orderbook snapshot/delta messages.
Uses config.py URLs and proper v2 header-based auth (not in-band auth).
"""
import asyncio
import json
import base64
import time
import ssl
import certifi
import requests
import websockets
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from config import KALSHI_API_KEY, KALSHI_PRIVATE_KEY, KALSHI_WS_URL, KALSHI_REST_URL, KALSHI_SERIES


def get_headers(method, path):
    private_key = load_pem_private_key(KALSHI_PRIVATE_KEY.encode(), password=None)
    ts = int(time.time() * 1000)
    msg = f"{ts}{method}{path}"
    sig = private_key.sign(
        msg.encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    return {
        "KALSHI-ACCESS-KEY": KALSHI_API_KEY,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        "KALSHI-ACCESS-TIMESTAMP": str(ts)
    }


async def diag_orderbook():
    # Discover 15m ticker via REST v2
    rest_path = "/trade-api/v2/markets"
    headers = get_headers("GET", rest_path)
    res = requests.get(f"{KALSHI_REST_URL}{rest_path}",
                       params={"series_ticker": KALSHI_SERIES, "status": "open"},
                       headers=headers, timeout=10)
    
    print(f"REST Status: {res.status_code}")
    markets = res.json().get("markets", [])
    if not markets:
        print("No open KXBTC15M markets found.")
        return
    
    ticker = markets[0]["ticker"]
    print(f"Diagnosing ticker: {ticker}")

    # Connect to WS with signed headers (v2 pattern)
    ws_path = "/trade-api/ws/v2"
    ws_headers = get_headers("GET", ws_path)
    ws_url = f"{KALSHI_WS_URL}{ws_path}"
    
    print(f"Connecting to: {ws_url}")
    ctx = ssl.create_default_context(cafile=certifi.where())
    
    async with websockets.connect(ws_url, additional_headers=ws_headers, ssl=ctx) as ws:
        print("Connected!")
        
        # Subscribe to orderbook
        await ws.send(json.dumps({
            "id": 1,
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta"],
                "market_tickers": [ticker]
            }
        }))
        
        print("Waiting for orderbook data...")
        count = 0
        while count < 10:
            msg = await asyncio.wait_for(ws.recv(), timeout=15)
            data = json.loads(msg)
            msg_type = data.get("type")
            payload = data.get("msg", data)
            
            if msg_type in ("orderbook_snapshot", "snapshot"):
                print(f"\n--- SNAPSHOT ---")
                # v2 uses 'yes' and 'no' lists
                yes = payload.get("yes", payload.get("yes_dollars_fp", []))
                no = payload.get("no", payload.get("no_dollars_fp", []))
                print(f"YES entries: {len(yes)}")
                print(f"NO entries: {len(no)}")
                if no:
                    print("Sample NO orderbook entries (Price, Vol):")
                    for entry in no[:5]:
                        print(f"  {entry[0]}: {entry[1]}")
                count += 1
            elif msg_type in ("orderbook_delta", "delta"):
                print(f"\n--- DELTA ---")
                print(f"  {json.dumps(payload, indent=2)}")
                count += 1
            else:
                print(f"Other message type: {msg_type}")
                print(f"  {json.dumps(data, indent=2)}")

if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(diag_orderbook())
