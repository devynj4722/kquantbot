"""Quick check: what fields does the Kalshi market object return for strike price?"""
import requests, json
from config import KALSHI_REST_URL, KALSHI_SERIES

r = requests.get(f"{KALSHI_REST_URL}/markets",
                 params={"limit": 1, "series_ticker": KALSHI_SERIES, "status": "open"},
                 timeout=10)
m = r.json().get("markets", [{}])[0]
# Print all keys so we can identify the strike field
print(json.dumps({k: v for k, v in m.items()}, indent=2))
