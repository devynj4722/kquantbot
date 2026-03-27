import asyncio
import json
import websockets
import aiohttp
import ssl
import certifi
import time

async def test_coinbase():
    url = "wss://ws-feed.exchange.coinbase.com"
    print(f"Testing Coinbase WS: {url}")
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    try:
        async with websockets.connect(url, ssl=ssl_context) as ws:
            print("Connected to Coinbase.")
            await ws.send(json.dumps({
                "type": "subscribe",
                "product_ids": ["BTC-USD"],
                "channels": ["ticker", "heartbeat"]
            }))
            print("Subscription sent. Waiting for messages...")
            for _ in range(5):
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(msg)
                print(f"Recv: {data.get('type')} - {data.get('price', 'No Price')}")
    except Exception as e:
        print(f"Coinbase WS Error: {e}")

async def test_oi():
    print("\nTesting OI Feeds...")
    async with aiohttp.ClientSession() as session:
        # Bybit
        bybit_url = "https://api.bytick.com/v5/market/open-interest?category=linear&symbol=BTCUSDT"
        try:
            async with session.get(bybit_url, timeout=10) as r:
                print(f"Bybit ({bybit_url}) Status: {r.status}")
                if r.status != 200:
                    print(f"Bybit Response: {await r.text()}")
        except Exception as e:
            print(f"Bybit Error: {e}")

        # BitMEX
        bmex_url = "https://www.bitmex.com/api/v1/instrument?symbol=XBTUSD&columns=openInterest"
        try:
            async with session.get(bmex_url, timeout=10) as r:
                print(f"BitMEX ({bmex_url}) Status: {r.status}")
                if r.status != 200:
                    print(f"BitMEX Response: {await r.text()}")
        except Exception as e:
            print(f"BitMEX Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_coinbase())
    asyncio.run(test_oi())
