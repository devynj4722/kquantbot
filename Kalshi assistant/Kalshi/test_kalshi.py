import base64
import json
import time
import asyncio
import websockets
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from config import KALSHI_API_KEY, KALSHI_PRIVATE_KEY, KALSHI_WS_URL, KALSHI_TICKER

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


async def test_kalshi():
    current_time = int(time.time() * 1000)
    
    signature = sign_kalshi(KALSHI_PRIVATE_KEY, "GET", "/trade-api/ws/v2", current_time)
    
    headers = {
        "KALSHI-ACCESS-KEY": KALSHI_API_KEY,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": str(current_time)
    }

    print("Connecting with headers:", headers)
    
    try:
        async with websockets.connect(KALSHI_WS_URL, additional_headers=headers) as ws:
            print("Connected to Kalshi!")
            # Auth is handled via headers, so just subscribe now
            sub_msg = {
                "id": 1,
                "cmd": "subscribe",
                "params": {
                    "channels": ["orderbook_delta"],
                    "market_tickers": [KALSHI_TICKER]
                }
            }
            await ws.send(json.dumps(sub_msg))
            print("Sent subscription request")
            
            for _ in range(3):
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                print("Received:", msg)
    except websockets.exceptions.InvalidStatusCode as e:
        print("Invalid status code:", e.status_code)
        
        # Check standard kalshi auth rejection headers if they exist
        for k, v in e.headers.items():
            print(f"{k}: {v}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        
if __name__ == "__main__":
    asyncio.run(test_kalshi())
