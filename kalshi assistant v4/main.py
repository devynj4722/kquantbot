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
    # Auto-launch KCI standalone widget
    import subprocess
    import sys
    import atexit
    
    # Run the widget in the background without tying up a console window
    widget_cmd = [sys.executable, "kci_widget.py"]
    widget_proc = subprocess.Popen(widget_cmd, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    
    def cleanup():
        try:
            widget_proc.terminate()
        except:
            pass
            
    atexit.register(cleanup)

    app = GUIDisplay()
    executor = TradeExecutor(ui_display=app)

    # Run async data pipeline in background daemon thread
    bg = threading.Thread(target=run_asyncio_loop, args=(app, executor), daemon=True)
    bg.start()

    app.run()
