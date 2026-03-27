# check_keys.py
import os
import base64
import time
from dotenv import load_dotenv
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

load_dotenv()

def check():
    api_key = os.getenv("KALSHI_API_KEY", "").strip()
    raw_key = os.getenv("KALSHI_PRIVATE_KEY", "")
    
    print(f"--- Diagnostic Report ---")
    print(f"API Key: {api_key[:5]}...{api_key[-5:] if len(api_key)>10 else ''}")
    print(f"Raw Key Length: {len(raw_key)} characters")
    
    # Strip quotes
    clean_key = raw_key.strip().strip('"').strip("'").replace("\\n", "\n")
    print(f"Cleaned Key Length: {len(clean_key)} characters")
    
    if "-----BEGIN RSA PRIVATE KEY-----" not in clean_key:
        print("ERROR: Key does not contain PEM header!")
        return

    try:
        import requests
        print(f"--- Live Connection Test ---")
        ts = int(time.time() * 1000)
        path = "/trade-api/v2/markets"
        msg = f"{ts}GET{path}"
        sig = pk.sign(
            msg.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        headers = {
            "KALSHI-ACCESS-KEY": api_key,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": str(ts),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://demo.kalshi.co/"
        }
        url = f"https://demo.kalshi.co{path}"
        params = {"limit": 1, "status": "open"}
        r = requests.get(url, headers=headers, params=params, timeout=10)
        print(f"HTTP Status: {r.status_code}")
        if r.status_code == 200:
            print("SUCCESS: Connected to Kalshi Demo API!")
            print(f"Data: {r.text[:100]}...")
        else:
            print(f"FAILED: {r.status_code}")
            print(f"Response: {r.text[:200]}")
            
    except Exception as e:
        print(f"ERROR: Live test failed: {e}")

if __name__ == "__main__":
    check()
