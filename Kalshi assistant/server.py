import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading

from math_engine import MathEngine
from data_ingestion import DataIngestion
from trade_executor import TradeExecutor

# FastAPI app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.last_state = None
        self.logs = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send latest state immediately upon connect
        if self.last_state:
            await websocket.send_json(self.last_state)
        # Send recent logs
        for log in self.logs[-50:]:  # Last 50 logs
            await websocket.send_json(log)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        if message.get("type") == "state":
            self.last_state = message
        elif message.get("type") in ("info", "error"):
            self.logs.append(message)
            if len(self.logs) > 200:
                self.logs.pop(0)

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, wait for client messages if any
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


class WebUIDispatcher:
    """Mock UI class that forwards updates to the web clients via FastAPI WebSocket."""
    def __init__(self, loop):
        self.loop = loop

    def update_state(self, current_price: float, signals: dict):
        # Fire and forget into the event loop
        message = {
            "type": "state",
            "current_price": current_price,
            "signals": signals
        }
        asyncio.run_coroutine_threadsafe(manager.broadcast(message), self.loop)

    def log_info(self, message: str):
        print(f"INFO: {message}")
        msg = {
            "type": "info",
            "message": message
        }
        asyncio.run_coroutine_threadsafe(manager.broadcast(msg), self.loop)

    def log_error(self, message: str):
        print(f"ERROR: {message}")
        msg = {
            "type": "error",
            "message": message
        }
        asyncio.run_coroutine_threadsafe(manager.broadcast(msg), self.loop)


async def run_data_ingestion(loop):
    ui = WebUIDispatcher(loop)
    math_engine = MathEngine()
    executor = TradeExecutor(ui_display=ui)
    ingestion = DataIngestion(math_engine=math_engine, ui_display=ui, trade_executor=executor)
    await ingestion.start()


@app.on_event("startup")
async def startup_event():
    # Start the data ingestion pipeline in the same event loop
    loop = asyncio.get_running_loop()
    asyncio.create_task(run_data_ingestion(loop))


if __name__ == "__main__":
    # Run the server
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
