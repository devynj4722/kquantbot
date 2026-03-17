import aiohttp
import asyncio
import json
import websockets
from config import (KALSHI_WS_URL, KALSHI_REST_URL, KALSHI_SERIES,
                    COINBASE_WS_URL, COINBASE_PRODUCT_ID, COINBASE_REST_URL,
                    KALSHI_API_KEY, KALSHI_PRIVATE_KEY, MAX_OPEN_POSITIONS)
import time
import base64
from collections import deque
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
import trade_logger
import ssl
import certifi


class DataIngestion:
    def __init__(self, math_engine, ui_display, trade_executor=None):
        self.math_engine = math_engine
        self.ui_display = ui_display
        self.trade_executor = trade_executor
        self.current_btc_price = 0.0
        self.current_ticker = None
        self.binance_oi = 0.0
        self.binance_oi_source = "OFFLINE"
        self._last_oi_fetch = 0
        self._last_anomaly_snapshot = 0
        self._last_price_time = 0         # Specifically for watchdog
        self._last_signal_time = 0        # For internal message tracking (Socket health)
        self._last_push_time = 0          # For signal throttling
        self.best_no_ask = 0.5
        self._no_ask_history = deque(maxlen=5)   # for implied prob trend
        self._open_positions = 0          # guard: don't over-trade
        self._last_trade_ticker = None    # fire once per 15m window
        self._last_signal_time = 0        # throttle signal calculations

        self.kalshi_private_key = None
        if KALSHI_PRIVATE_KEY:
            self.kalshi_private_key = load_pem_private_key(
                KALSHI_PRIVATE_KEY.encode('utf-8'), password=None)
        
        # Create SSL context for Mac/System certificate issues
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())

    # ── Coinbase candle seed ──────────────────────────────────────────────────
    async def _seed_candles_from_rest(self):
        """Fetches the last 50 1-minute candles from Coinbase REST to warm up the math engine."""
        session = await self.trade_executor.get_session()
        try:
            url = f"{COINBASE_REST_URL}/products/{COINBASE_PRODUCT_ID}/candles"
            async with session.get(url, params={"granularity": 60}, timeout=10) as r:
                candles = await r.json()  # [[time, low, high, open, close, volume], ...]
                if not isinstance(candles, list) or not candles:
                    return
                # API returns newest first; reverse so oldest is index 0
                candles = sorted(candles, key=lambda x: x[0])
                for c in candles[-50:]:
                    ts, low, high, open_, close, volume = c
                    self.math_engine.add_kline({
                        'timestamp': ts * 1000,
                        'open': float(open_),
                        'high': float(high),
                        'low': float(low),
                        'close': float(close),
                        'volume': float(volume)
                    })
                self.ui_display.log_info(f"Seeded {min(50, len(candles))} historical 1m candles.")
        except Exception as e:
            self.ui_display.log_error(f"Candle seed error: {e}")

    # ── Kalshi helpers ────────────────────────────────────────────────────────
    async def _get_active_15m_ticker(self) -> tuple:
        session = await self.trade_executor.get_session()
        try:
            async with session.get(f"{KALSHI_REST_URL}/markets",
                                   params={"limit": 1, "series_ticker": KALSHI_SERIES, "status": "open"},
                                   timeout=10) as r:
                data = await r.json()
                markets = data.get("markets", [])
                if markets:
                    m = markets[0]
                    ticker = m["ticker"]
                    from datetime import datetime, timezone
                    close_ts = datetime.fromisoformat(
                        m["close_time"].replace("Z", "+00:00")).timestamp()
                    self.strike_price = float(m.get("floor_strike") or 0)
                    closes_in = int(close_ts - time.time())
                    self.ui_display.log_info(
                        f"Market: {ticker} | Strike: ${self.strike_price:,.2f} (closes in {closes_in}s)")
                    return ticker, close_ts
                self.ui_display.log_error("No open 15m markets found.")
                return None, None
        except Exception as e:
            self.ui_display.log_error(f"REST error: {e}")
            return None, None

    def _make_kalshi_headers(self) -> dict:
        if not (self.kalshi_private_key and KALSHI_API_KEY):
            return {}
        ts = int(time.time() * 1000)
        sig = self.kalshi_private_key.sign(
            f"{ts}GET/trade-api/ws/v2".encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return {
            "KALSHI-ACCESS-KEY": KALSHI_API_KEY,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": str(ts)
        }

    # ── Orderbook processing ──────────────────────────────────────────────────
    def _process_snapshot(self, msg: dict):
        self.math_engine.bids.clear()
        self.math_engine.asks.clear()
        best_no = None
        for entry in msg.get("no_dollars_fp", []):
            no_p, vol = float(entry[0]), float(entry[1])
            self.math_engine.update_orderbook('ask', no_p, vol)
            self.math_engine.update_orderbook('bid', round(1.0 - no_p, 4), vol)
            if best_no is None or no_p < best_no:
                best_no = no_p
        if best_no is not None:
            self.best_no_ask = best_no
            self._no_ask_history.append(best_no)

    def _process_delta(self, msg: dict):
        price = float(msg.get("price_dollars", 0))
        delta = float(msg.get("delta_fp", 0))
        side = msg.get("side", "no")
        if side == "no":
            self.math_engine.delta_orderbook('ask', price, delta)
            self.math_engine.delta_orderbook('bid', round(1.0 - price, 4), delta)
            if self.math_engine.asks:
                self.best_no_ask = min(self.math_engine.asks.keys())
                self._no_ask_history.append(self.best_no_ask)
        else:
            self.math_engine.delta_orderbook('bid', price, delta)

    def _get_prob_trend(self) -> str:
        """Returns '▲' if YES implied prob is rising, '▼' if falling, '─' if flat."""
        if len(self._no_ask_history) < 2:
            return "─"
        # YES prob = 1 - no_ask; if no_ask is falling, YES is rising
        if self._no_ask_history[-1] < self._no_ask_history[0]:
            return "▲"
        elif self._no_ask_history[-1] > self._no_ask_history[0]:
            return "▼"
        return "─"

    def _get_ev(self, z_score: float = 0.0) -> tuple:
        market_p_win = round(1.0 - self.best_no_ask, 4)
        yes_price = market_p_win
        z_adj = max(-0.15, min(0.15, z_score * 0.03))
        model_p_win = max(0.05, min(0.95, 0.5 + z_adj))
        return model_p_win, round(1.0 - yes_price, 4), yes_price

    def _push_signals(self, ts: float = None):
        """Evaluate all signals and push to GUI."""
        z_score = self.math_engine.calculate_z_score(self.current_btc_price)
        p_win, pot_profit, pot_loss = self._get_ev(z_score=z_score)
        signals = self.math_engine.evaluate_signals(
            self.current_btc_price, p_win_estimate=p_win,
            pot_profit=pot_profit, pot_loss=pot_loss)
        signals['prob_trend'] = self._get_prob_trend()
        signals['time_left'] = max(0, int((self.market_close_ts or 0) - time.time()))
        signals['p_win_estimate'] = p_win

        # ATR Distance: how many ATRs is BTC from the strike?
        atr = signals.get('atr', 0.0)
        if atr > 0 and self.strike_price > 0:
            atr_distance = (self.current_btc_price - self.strike_price) / atr
        else:
            atr_distance = 0.0
        signals['atr_distance'] = atr_distance
        signals['strike_price'] = self.strike_price
        signals['binance_oi'] = self.binance_oi
        signals['oi_source'] = self.binance_oi_source
        signals['cvd'] = self.math_engine.cvd

        # Detect Market Anomalies (Fixed-interval snapshots)
        now = time.time()
        if (now - self._last_anomaly_snapshot) >= 1.0:
            self.math_engine.update_snapshots(self.current_btc_price)
            self._last_anomaly_snapshot = now
            
        signals['anomalies'] = self.math_engine.get_active_anomalies()

        self.ui_display.update_state(current_price=self.current_btc_price, signals=signals, ts=ts)
        self._last_signal_time = time.time()

        # Auto-trade if prime setup and under position limit
        if (signals['is_good_setup'] and self.trade_executor and
                self._open_positions < MAX_OPEN_POSITIONS and
                self.current_ticker != self._last_trade_ticker):
            direction = signals.get('signal_direction', 'NEUTRAL')
            if direction != 'NEUTRAL':
                side = 'yes' if direction == 'UP' else 'no'
                # Launch trade in background task to not block math loop
                asyncio.create_task(self.trade_executor.place_order(
                    ticker=self.current_ticker, side=side,
                    yes_price=round(1.0 - self.best_no_ask, 4)))
                trade_logger.log_signal(
                    ticker=self.current_ticker,
                    direction=direction,
                    ev=signals['ev'],
                    z_score=signals['z_score'],
                    rsi=signals.get('rsi', 0),
                    macd_histogram=signals.get('macd', {}).get('histogram', 0),
                    market_p_win=round(1.0 - self.best_no_ask, 4),
                    yes_price=round(1.0 - self.best_no_ask, 4),
                    dry_run=True)  # trade_executor enforces DRY_RUN internally
                self._last_trade_ticker = self.current_ticker
                self._open_positions += 1

    # ── Coinbase WebSocket ────────────────────────────────────────────────────
    async def connect_coinbase(self):
        while True:
            self.ui_display.log_info("Connecting to Coinbase WS...")
            try:
                # Add ping_interval and ping_timeout to detect dead sockets
                # Increased max_size to 16MB to handle high-volume volatility spikes
                async with websockets.connect(
                    COINBASE_WS_URL, 
                    ssl=self.ssl_context,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=10,
                    max_size=16 * 1024 * 1024 
                ) as ws:
                    self.ui_display.log_info("Coinbase WS Connected (with Heartbeat).")
                    await ws.send(json.dumps({
                        "type": "subscribe",
                        "product_ids": [COINBASE_PRODUCT_ID],
                        "channels": ["ticker", "heartbeat"]
                    }))
                    last_candle_time = int(time.time()) // 60 * 60
                    mock_candle = {"low": float('inf'), "high": 0.0, "open": 0.0, "close": 0.0}

                    while True:
                        # Wait maximum 10 seconds for a message before assuming connection is dead
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=10)
                            data = json.loads(msg)
                            self._last_signal_time = time.time() # Healthy Socket
                            # Console heartbeat for debugging
                            if data.get('type') == 'ticker':
                                self._last_price_time = time.time() # Actual Data
                                if int(time.time()) % 15 == 0:
                                    print(f"CB TICKER: {data.get('price')} (Price health: OK)")
                            elif data.get('type') == 'heartbeat':
                                if int(time.time()) % 15 == 0:
                                    print(f"CB HEARTBEAT: Socket health: OK (Price delay? {time.time() - self._last_price_time:.1f}s)")
                        except asyncio.TimeoutError:
                            self.ui_display.log_error("Coinbase WS Timeout - No data/heartbeat for 10s. Reconnecting...")
                            break
                        except Exception as e:
                            self.ui_display.log_error(f"CB RECV ERROR: {e}")
                            break

                        if data.get('type') == 'ticker' and 'price' in data:
                            price = float(data['price'])
                            self.current_btc_price = price

                            # Update CVD
                            side = data.get('side')
                            last_size = float(data.get('last_size', 0))
                            if side and last_size:
                                self.math_engine.update_cvd(side, last_size)

                            now_float = time.time()
                            candle_start = int(now_float) // 60 * 60
                            if mock_candle["open"] == 0.0:
                                mock_candle["open"] = price
                            mock_candle["high"] = max(mock_candle["high"], price)
                            mock_candle["low"] = min(mock_candle["low"], price)
                            mock_candle["close"] = price

                            if candle_start > last_candle_time:
                                self.math_engine.add_kline({
                                    'timestamp': last_candle_time * 1000,
                                    'open': mock_candle["open"],
                                    'high': mock_candle["high"],
                                    'low': mock_candle["low"],
                                    'close': mock_candle["close"],
                                    'volume': float(data.get('last_size', 100.0))
                                })
                                last_candle_time = candle_start
                                mock_candle = {"low": float('inf'), "high": 0.0,
                                              "open": price, "close": price}
                            
                            # High-speed price update (Immediate)
                            reception_ts = time.time()
                            self.ui_display.update_price_only(price, ts=reception_ts)
                            
                            # Throttled Signal update (Heavy math - 5 times per second max)
                            if (now_float - self._last_push_time) >= 0.2:
                                try:
                                    self._push_signals(ts=reception_ts)
                                except Exception as push_err:
                                    self.ui_display.log_error(f"Signal Push Error: {push_err}")
                                self._last_push_time = now_float
            except Exception as e:
                self.ui_display.log_error(f"Coinbase WS Error: {e}")
            
            self.ui_display.log_info("Retrying Coinbase connection in 5s...")
            await asyncio.sleep(5)

    # ── Kalshi WebSocket ──────────────────────────────────────────────────────
    async def connect_kalshi(self):
        if not KALSHI_API_KEY:
            self.ui_display.log_error("CRITICAL: KALSHI_API_KEY missing in .env")
            return

        while True:
            self.ui_display.log_info("Checking for active Kalshi markets...")
            ticker, close_ts = await self._get_active_15m_ticker()
            if not ticker:
                self.ui_display.log_error("No active Kalshi markets. Retrying in 30s...")
                await asyncio.sleep(30)
                continue

            self.current_ticker = ticker
            self.market_close_ts = close_ts

            self.ui_display.log_info(f"Connecting to Kalshi WS for {ticker}...")
            try:
                headers = self._make_kalshi_headers()
                async with websockets.connect(
                    KALSHI_WS_URL, 
                    additional_headers=headers, 
                    ssl=self.ssl_context,
                    ping_interval=20,
                    ping_timeout=10,
                    max_size=16 * 1024 * 1024
                ) as ws:
                    self.ui_display.log_info(f"Kalshi WS Connected ({ticker})")
                    if ws.response.status_code in (401, 403):
                        self.ui_display.log_error(
                            "AUTH FAILED (401/403) — Kalshi API key may be expired. Check .env.")
                        await asyncio.sleep(60)
                        continue

                    await ws.send(json.dumps({
                        "id": 1, "cmd": "subscribe",
                        "params": {"channels": ["orderbook_delta"],
                                   "market_tickers": [ticker]}
                    }))

                    while True:
                        time_left = close_ts - time.time()
                        if time_left <= 10:
                            self.ui_display.log_info(f"Market {ticker} expiring, switching...")
                            break
                        try:
                            recv_timeout = min(20, max(1, time_left - 10))
                            data = json.loads(await asyncio.wait_for(ws.recv(), timeout=recv_timeout))
                            msg_type = data.get("type")
                            inner = data.get("msg", {})
                            if msg_type == "orderbook_snapshot":
                                self._process_snapshot(inner)
                            elif msg_type == "orderbook_delta":
                                self._process_delta(inner)
                            elif msg_type == "market_status" and inner.get("status") in ("finalized", "closed"):
                                break
                            if msg_type in ("orderbook_snapshot", "orderbook_delta"):
                                self._push_signals()
                                self._last_signal_time = time.time()
                        except asyncio.TimeoutError:
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            self.ui_display.log_info("Kalshi WS closed. Reconnecting...")
                            break
            except Exception as e:
                self.ui_display.log_error(f"Kalshi WS Error: {e}")
            await asyncio.sleep(2)

    async def _watchdog_task(self):
        """Monitors TICKER latency and forces full stack reset if hung > 10s."""
        # Initialize to now so we don't wait for the first signal to arm
        if self._last_price_time == 0:
            self._last_price_time = time.time()

        while True:
            await asyncio.sleep(2)
            lag = time.time() - self._last_price_time
            if lag > 10:
                self.ui_display.log_error(f"WATCHDOG: PRICE DATA HUNG for {lag:.1f}s. (Socket heartbeats? {time.time() - self._last_signal_time:.1f}s ago)")
                self.ui_display.log_error("FORCING RESTART...")
                raise RuntimeError(f"Price data hung for {lag:.1f}s")
            
            # Diagnostic periodic log
            if int(time.time()) % 10 == 0:
                p_delta = self.math_engine.price_history[-1] - self.math_engine.price_history[0] if self.math_engine.price_history else 0
                c_total = self.math_engine.cvd
                self.ui_display.log_info(f"DIAG: Price Δ ${p_delta:+.1f} | Total CVD: {c_total:+.1f} BTC")

    async def _fetch_oi_task(self):
        """Fetches BTC Open Interest from Bybit V5 (Primary) or BitMEX (Fallback)."""
        while True:
            try:
                session = await self.trade_executor.get_session()
                # Use api.bytick.com which is often more resilient to geoblocks
                bybit_url = "https://api.bytick.com/v5/market/open-interest?category=linear&symbol=BTCUSDT"
                async with session.get(bybit_url, timeout=10) as r:
                    if r.status == 200:
                        data = await r.json()
                        result = data.get('result', {}).get('list', [])
                        if result:
                            # Bybit Linear BTCUSDT OI is directly in BTC units
                            oi_btc = float(result[0].get('openInterest', 0))
                            if oi_btc > 0:
                                self.binance_oi = oi_btc
                                self.binance_oi_source = "BYB"
                                self.math_engine.update_oi(self.binance_oi)
                                self._last_oi_fetch = time.time()
                                continue # Successfully fetched from Bybit, skip BitMEX for this cycle
                    else:
                        if r.status in (403, 451):
                            self.ui_display.log_error(f"Bybit OI Blocked (HTTP {r.status}). Using BitMEX Fallback.")
                        else:
                            self.ui_display.log_error(f"Bybit OI Error {r.status}. Using BitMEX Fallback.")
                
                # Fallback to BitMEX (Canary scale)
                url = "https://www.bitmex.com/api/v1/instrument?symbol=XBTUSD&columns=openInterest"
                async with session.get(url, timeout=10) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data and isinstance(data, list):
                            oi_usd = float(data[0].get('openInterest', 0))
                            if self.current_btc_price > 0:
                                self.binance_oi = oi_usd / self.current_btc_price
                            else:
                                self.binance_oi = oi_usd / 60000.0 # fallback
                            self.binance_oi_source = "BMX"
                            self.math_engine.update_oi(self.binance_oi)
                            self._last_oi_fetch = time.time()
                    else:
                        self.ui_display.log_error(f"OI Source (BitMEX) HTTP {r.status}")
                        
            except Exception as e:
                self.ui_display.log_error(f"OI Fetch Error: {e}")
            await asyncio.sleep(30)
                    # This will kill the loops and allow asyncio.gather to restart (if we wrap it)
                    # For now, let's just log and rely on the websocket receive timeouts which are 10s.
                    # If recv timeout didn't work, we might need a more aggressive restart.

    async def start(self):
        self.ui_display.log_info("Starting Data Ingestion Pipeline...")
        
        while True:
            self._last_price_time = time.time() # Arm watchdog for PRICE
            self._last_signal_time = time.time()
            tasks = []
            try:
                # Run seed in background so it doesn't block live feed
                seed_task = asyncio.create_task(self._seed_candles_from_rest())
                
                tasks = [
                    asyncio.create_task(self.connect_coinbase()),
                    asyncio.create_task(self.connect_kalshi()),
                    asyncio.create_task(self._watchdog_task()),
                    asyncio.create_task(self._fetch_oi_task()),
                    seed_task
                ]
                
                # Wait for any task to fail or finish
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                
                # Check for exceptions
                for task in done:
                    if task.exception():
                        raise task.exception()
            except Exception as e:
                self.ui_display.log_error(f"PIPELINE CRASH: {e}")
            finally:
                # Clean up ALL tasks
                for t in tasks:
                    if not t.done():
                        t.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                self.ui_display.log_info("Restarting entire stack in 3s...")
                await asyncio.sleep(3)
