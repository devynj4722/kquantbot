"""
Diagnostic: test production Kalshi REST authentication directly
and show the full response body so we can see why 401 is returned.
"""
import base64
import time
import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from config import KALSHI_API_KEY, KALSHI_PRIVATE_KEY, KALSHI_REST_URL

print(f"REST URL: {KALSHI_REST_URL}")
print(f"API Key: {KALSHI_API_KEY[:10]}...")

# Build signature
private_key = load_pem_private_key(KALSHI_PRIVATE_KEY.encode(), password=None)
ts = int(time.time() * 1000)
path = "/trade-api/v2/markets"
msg = f"{ts}GET{path}"
sig = private_key.sign(
    msg.encode(),
    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
    hashes.SHA256()
)
headers = {
    "KALSHI-ACCESS-KEY": KALSHI_API_KEY,
    "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
    "KALSHI-ACCESS-TIMESTAMP": str(ts)
}

# Make the REST call
url = f"{KALSHI_REST_URL}{path}"
print(f"\nHitting: {url}")
r = requests.get(url, params={"limit": 1, "series_ticker": "KXBTC15M", "status": "open"},
                 headers=headers)
print(f"HTTP Status: {r.status_code}")
print(f"Response: {r.text[:1000]}")
