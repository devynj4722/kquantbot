"""Quick check: what fields does the Kalshi market object return for strike price?"""
import requests, json, time, base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from config import KALSHI_REST_URL, KALSHI_SERIES, KALSHI_API_KEY, KALSHI_PRIVATE_KEY

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
                 headers=headers, timeout=10)
print(f"Status: {r.status_code}")
m = r.json().get("markets", [{}])[0]
# Print all keys so we can identify the strike field
print(json.dumps({k: v for k, v in m.items()}, indent=2))
