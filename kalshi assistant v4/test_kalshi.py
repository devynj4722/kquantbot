import base64
import json
import time
import asyncio
import ssl
import certifi
import requests
import websockets
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from config import KALSHI_API_KEY, KALSHI_PRIVATE_KEY, KALSHI_WS_URL, KALSHI_REST_URL, KALSHI_SERIES

def sign_kalshi(private_key_pem: str, method: str, path: str, timestamp_ms: int):
    # Load the private key
    private_key = load_pem_private_key(private_key_pem.encode('utf-8'), password=None)
    
    # Message to sign: timestamp + method + path
    msg_string = f"{timestamp_ms}{method}{path}"
    
    # RSA-PSS SHA256 signature
    signature = private_key.sign(
        msg_string.encode('utf-8'),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')


def discover_ticker():
    """Discover an active 15m BTC ticker from Kalshi REST API."""
    path = "/trade-api/v2/markets"
    ts = int(time.time() * 1000)
    signature = sign_kalshi(KALSHI_PRIVATE_KEY, "GET", path, ts)
    headers = {
        "KALSHI-ACCESS-KEY": KALSHI_API_KEY,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": str(ts)
    }
    r = requests.get(f"{KALSHI_REST_URL}{path}",
                     params={"limit": 1, "series_ticker": KALSHI_SERIES, "status": "open"},
                     headers=headers, timeout=10)
    print(f"REST Status: {r.status_code}")
    markets = r.json().get("markets", [])
    if markets:
        ticker = markets[0]["ticker"]
        print(f"Discovered ticker: {ticker}")
        return ticker
    print("No active markets found.")
    return None


async def test_kalshi():
    ticker = discover_ticker()
    if not ticker:
        return
    
    ws_path = "/trade-api/ws/v2"
    current_time = int(time.time() * 1000)
    
    signature = sign_kalshi(KALSHI_PRIVATE_KEY, "GET", ws_path, current_time)
    
    headers = {
        "KALSHI-ACCESS-KEY": KALSHI_API_KEY,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": str(current_time)
    }

    ws_url = f"{KALSHI_WS_URL}{ws_path}"
    print(f"Connecting to: {ws_url}")
    print(f"Headers: {headers}")
    
    ctx = ssl.create_default_context(cafile=certifi.where())
    
    try:
        async with websockets.connect(ws_url, additional_headers=headers, ssl=ctx) as ws:
            print("Connected to Kalshi!")
            # Subscribe to orderbook
            sub_msg = {
                "id": 1,
                "cmd": "subscribe",
                "params": {
                    "channels": ["orderbook_delta"],
                    "market_tickers": [ticker]
                }
            }
            await ws.send(json.dumps(sub_msg))
            print("Sent subscription request")
            
            for _ in range(3):
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                print("Received:", msg)
    except websockets.exceptions.InvalidStatusCode as e:
        print("Invalid status code:", e.status_code)
        for k, v in e.headers.items():
            print(f"{k}: {v}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        
if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_kalshi())
