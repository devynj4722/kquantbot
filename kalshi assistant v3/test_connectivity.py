import asyncio
import aiohttp
import json
import websockets
import time

async def test_coinbase():
    url = "wss://ws-feed.exchange.coinbase.com"
    print(f"Connecting to {url}...")
    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=10, open_timeout=10) as ws:
            print("Connected. Subscribing...")
            await ws.send(json.dumps({
                "type": "subscribe",
                "product_ids": ["BTC-USD"],
                "channels": ["ticker", "heartbeat"]
            }))
            
            start = time.time()
            count = 0
            while time.time() - start < 30:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(msg)
                    count += 1
                    print(f"[{count}] Received type: {data.get('type')} at {time.time()}")
                    if count > 10: break
                except asyncio.TimeoutError:
                    print("TIMEOUT: No message for 5 seconds.")
            print(f"Test finished. Received {count} messages.")
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_coinbase())
