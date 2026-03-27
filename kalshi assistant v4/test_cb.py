import asyncio
import json
import websockets

async def test_cb():
    uri = "wss://ws-feed.exchange.coinbase.com"
    async with websockets.connect(uri) as ws:
        sub = {"type": "subscribe", "product_ids": ["BTC-USD"], "channels": ["ticker"]}
        await ws.send(json.dumps(sub))
        for i in range(5):
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(msg)
            print(f"Msg {i}: type={data.get('type')}, price={data.get('price', 'N/A')}")

if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_cb())
