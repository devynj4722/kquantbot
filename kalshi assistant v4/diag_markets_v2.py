
import requests
import time
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from config import KALSHI_API_KEY, KALSHI_PRIVATE_KEY, KALSHI_REST_URL

def get_headers(method, path):
    private_key = serialization.load_pem_private_key(
        KALSHI_PRIVATE_KEY.encode(),
        password=None
    )
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

def diag_markets():
    path = "/trade-api/v2/markets"
    url = f"{KALSHI_REST_URL}{path}"
    headers = get_headers("GET", path)
    
    print(f"Querying Kalshi REST: {url}")
    params = {"series_ticker": "KXBTC15M", "status": "open"}
    res = requests.get(url, params=params, headers=headers)
    
    if res.status_code != 200:
        print(f"Error: {res.status_code}")
        print(res.text)
        return

    data = res.json()
    markets = data.get("markets", [])
    print(f"Found {len(markets)} markets.")
    
    if markets:
        m = markets[0]
        print("\nStructure of first market:")
        import json
        print(json.dumps(m, indent=2))
        
        # Check for strike keys
        print("\nStrike keys identified:")
        print(f"  floor_strike: {m.get('floor_strike')}")
        print(f"  cap_strike: {m.get('cap_strike')}")
        print(f"  strike_price: {m.get('strike_price')}")
        print(f"  target: {m.get('target')}")

if __name__ == "__main__":
    diag_markets()
