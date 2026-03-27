import asyncio
from data_ingestion import DataIngestion

class DummyUI:
    def log_info(self, msg): print("[INFO]", msg)
    def log_error(self, msg): print("[ERROR]", msg)

class DummyExecutor:
    async def get_session(self):
        import aiohttp
        if not hasattr(self, 'session'):
            self.session = aiohttp.ClientSession()
        return self.session

async def test():
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    di = DataIngestion(None, DummyUI(), DummyExecutor())
    
    ticker, close_ts = await di._get_active_15m_ticker()
    print("Ticker:", ticker, "Close TS:", close_ts)
    
if __name__ == "__main__":
    asyncio.run(test())
