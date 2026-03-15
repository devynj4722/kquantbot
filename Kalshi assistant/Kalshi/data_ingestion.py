import asyncio
import json
import websockets
import requests
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


class DataIngestion:
    def __init__(self, math_engine, ui_display, trade_executor=None):
        self.math_engine = math_engine
        self.ui_display = ui_display
        self.trade_executor = trade_executor
        self.current_btc_price = 0.0
        self.current_ticker = None
        self.market_close_ts = None
        self.strike_price = 0.0             # BTC price the Kalshi contract resolves at
        self.best_no_ask = 0.5
        self._no_ask_history = deque(maxlen=5)   # for implied prob trend
        self._open_positions = 0          # guard: don't over-trade
        self._last_trade_ticker = None    # fire once per 15m window

        self.kalshi_private_key = None
        if KALSHI_PRIVATE_KEY:
            self.kalshi_private_key = load_pem_private_key(
                KALSHI_PRIVATE_KEY.encode('utf-8'), password=None)

    # ── Coinbase candle seed ──────────────────────────────────────────────────
    def _seed_candles_from_rest(self):
        """Fetches the last 50 1-minute candles from Coinbase REST to warm up the math engine."""
        try:
            url = f"{COINBASE_REST_URL}/products/{COINBASE_PRODUCT_ID}/candles"
            r = requests.get(url, params={"granularity": 60}, timeout=10)
            candles = r.json()  # [[time, low, high, open, close, volume], ...]
            if not isinstance(candles, list) or not candles:
                return
            # API returns newest first; reverse so oldest is index 0
            candles = sorted(candles, key=lambda c: c[0])
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
    def _get_active_15m_ticker(self) -> tuple:
        try:
            r = requests.get(f"{KALSHI_REST_URL}/markets",
                             params={"limit": 1, "series_ticker": KALSHI_SERIES, "status": "open"},
                             timeout=10)
            markets = r.json().get("markets", [])
            if markets:
                m = markets[0]
                ticker = m["ticker"]
                from datetime import datetime, timezone
                close_ts = datetime.fromisoformat(
                    m["close_time"].replace("Z", "+00:00")).timestamp()
                # floor_strike is the BTC price the contract resolves against
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

    def _push_signals(self):
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

        self.ui_display.update_state(current_price=self.current_btc_price, signals=signals)

        # Auto-trade if prime setup and under position limit
        if (signals['is_good_setup'] and self.trade_executor and
                self._open_positions < MAX_OPEN_POSITIONS and
                self.current_ticker != self._last_trade_ticker):
            direction = signals.get('signal_direction', 'NEUTRAL')
            if direction != 'NEUTRAL':
                side = 'yes' if direction == 'UP' else 'no'
                self.trade_executor.place_order(
                    ticker=self.current_ticker, side=side,
                    yes_price=round(1.0 - self.best_no_ask, 4))
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
        try:
            async with websockets.connect(COINBASE_WS_URL) as ws:
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "product_ids": [COINBASE_PRODUCT_ID],
                    "channels": ["ticker"]
                }))
                last_candle_time = int(time.time()) // 60 * 60
                mock_candle = {"low": float('inf'), "high": 0.0, "open": 0.0, "close": 0.0}

                while True:
                    data = json.loads(await ws.recv())
                    if data.get('type') == 'ticker' and 'price' in data:
                        price = float(data['price'])
                        self.current_btc_price = price

                        now = int(time.time())
                        candle_start = now // 60 * 60
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
                        self._push_signals()
        except Exception as e:
            self.ui_display.log_error(f"Coinbase WS Error: {e}")
            await asyncio.sleep(5)
            await self.connect_coinbase()

    # ── Kalshi WebSocket ──────────────────────────────────────────────────────
    async def connect_kalshi(self):
        while True:
            ticker, close_ts = self._get_active_15m_ticker()
            if not ticker:
                await asyncio.sleep(30)
                continue

            self.current_ticker = ticker
            self.market_close_ts = close_ts

            try:
                headers = self._make_kalshi_headers()
                async with websockets.connect(KALSHI_WS_URL, additional_headers=headers) as ws:
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
                        except asyncio.TimeoutError:
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            self.ui_display.log_info("Kalshi WS closed. Reconnecting...")
                            break
            except Exception as e:
                self.ui_display.log_error(f"Kalshi WS Error: {e}")
            await asyncio.sleep(2)

    async def start(self):
        # Seed historical candles before entering live loop
        self._seed_candles_from_rest()
        await asyncio.gather(
            self.connect_coinbase(),
            self.connect_kalshi()
        )
