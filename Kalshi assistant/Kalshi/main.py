import asyncio
import threading
from math_engine import MathEngine
from gui_display import GUIDisplay
from data_ingestion import DataIngestion
from trade_executor import TradeExecutor


def run_asyncio_loop(ui, executor):
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        math_engine = MathEngine()
        ingestion = DataIngestion(math_engine=math_engine, ui_display=ui,
                                  trade_executor=executor)
        loop.run_until_complete(ingestion.start())
    except Exception as e:
        ui.log_error(f"Fatal Error: {e}")


if __name__ == "__main__":
    app = GUIDisplay()
    executor = TradeExecutor(ui_display=app)

    # Start system tray if available
    app._setup_tray()

    # Run async data pipeline in background daemon thread
    bg = threading.Thread(target=run_asyncio_loop, args=(app, executor), daemon=True)
    bg.start()

    app.mainloop()
