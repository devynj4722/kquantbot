import pandas as pd
import numpy as np
from collections import deque
from config import ATR_PERIODS, Z_SCORE_THRESHOLD, EV_THRESHOLD, MIN_WALL_VOLUME, ORDERBOOK_PRICE_BUCKET_SIZE

RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9


class MathEngine:
    def __init__(self):
        self.klines = []
        self.bids = {}
        self.asks = {}
        self.cvd = 0.0  # Cumulative Volume Delta
        self.cvd_history = deque(maxlen=3600)   # 1-second snapshots (60 minutes)
        self.oi_history = deque(maxlen=120)    # 30-second snaphots (60 minutes)
        self.price_history = deque(maxlen=3600) # 1-second snapshots (60 minutes)

    def add_kline(self, kline_data):
        """Adds OHLCV candle dict. Keeps buffer bounded."""
        self.klines.append(kline_data)
        max_len = max(ATR_PERIODS, RSI_PERIOD, MACD_SLOW + MACD_SIGNAL) * 3
        if len(self.klines) > max_len:
            self.klines.pop(0)

    def _close_series(self) -> pd.Series:
        if not self.klines:
            return pd.Series(dtype=float)
        df = pd.DataFrame(self.klines)
        if 'close' not in df.columns:
            return pd.Series(dtype=float)
        return df['close']

    # ── ATR ───────────────────────────────────────────────────────────────────
    def calculate_atr(self) -> float:
        if len(self.klines) < ATR_PERIODS + 1:
            return 0.0
        df = pd.DataFrame(self.klines)
        if 'close' not in df.columns or 'high' not in df.columns or 'low' not in df.columns:
            return 0.0
        df['prev_close'] = df['close'].shift(1)
        df['tr'] = df[['high', 'prev_close']].max(axis=1) - df[['low', 'prev_close']].min(axis=1)
        atr = df['tr'].rolling(window=ATR_PERIODS).mean().iloc[-1]
        return float(atr) if not pd.isna(atr) else 0.0

    # ── Volatility Compression Z-Score ───────────────────────────────────────
    def calculate_z_score(self, current_price: float) -> float:
        """
        Volatility Compression Z-Score.

        Formula:
          1. base_z     = (price - rolling_mean) / ATR  — how many ATRs from mean
          2. vol_ratio  = ATR_short / ATR_long           — < 1 means volatility is compressed
          3. vc_z       = base_z / max(vol_ratio, 0.3)  — amplify in squeeze, cap div

        Why better than standard Z-Score:
          - ATR normalisation makes it scale-adaptive and robust to price level changes
          - vol_ratio < 1 (squeeze) pushes vc_z higher, flagging high-probability breakouts
          - vol_ratio > 1 (expansion) dampens the signal to avoid chasing breakouts
        """
        needed = ATR_PERIODS + 1
        if len(self.klines) < needed:
            return 0.0

        df = pd.DataFrame(self.klines)
        if 'close' not in df.columns or 'high' not in df.columns or 'low' not in df.columns:
            return 0.0
        closes = df['close']
        df['prev_close'] = closes.shift(1)
        df['tr'] = (df[['high', 'prev_close']].max(axis=1)
                    - df[['low', 'prev_close']].min(axis=1))

        atr_short = df['tr'].rolling(ATR_PERIODS).mean().iloc[-1]
        # Long-term ATR uses 3x the window for historical context
        atr_long  = df['tr'].rolling(min(ATR_PERIODS * 3, len(df))).mean().iloc[-1]

        if pd.isna(atr_short) or atr_short == 0:
            return 0.0

        mean_price = closes.rolling(ATR_PERIODS).mean().iloc[-1]
        if pd.isna(mean_price):
            return 0.0

        base_z = (current_price - mean_price) / atr_short

        if not pd.isna(atr_long) and atr_long > 0:
            vol_ratio = atr_short / atr_long
            # Clamp divisor so extreme compression doesn't blow up the signal
            vc_z = base_z / max(vol_ratio, 0.3)
        else:
            vc_z = base_z  # fallback: no long history yet

        return float(np.clip(vc_z, -6.0, 6.0))

    # ── RSI ───────────────────────────────────────────────────────────────────
    def calculate_rsi(self) -> float:
        """Computes 14-period RSI. Returns 0 if insufficient data."""
        if len(self.klines) < RSI_PERIOD + 1:
            return 0.0
        closes = self._close_series()
        delta = closes.diff()
        gain = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
        loss = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        return float(val) if not pd.isna(val) else 50.0

    # ── MACD ──────────────────────────────────────────────────────────────────
    def calculate_macd(self) -> dict:
        """Returns dict with macd_line, signal_line, histogram. Zeros if insufficient data."""
        needed = MACD_SLOW + MACD_SIGNAL
        if len(self.klines) < needed:
            return {'macd_line': 0.0, 'signal_line': 0.0, 'histogram': 0.0}
        closes = self._close_series()
        ema_fast = closes.ewm(span=MACD_FAST, adjust=False).mean()
        ema_slow = closes.ewm(span=MACD_SLOW, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
        histogram = macd_line - signal_line
        return {
            'macd_line': float(macd_line.iloc[-1]),
            'signal_line': float(signal_line.iloc[-1]),
            'histogram': float(histogram.iloc[-1])
        }

    # ── Signal Direction ──────────────────────────────────────────────────────
    def get_signal_direction(self, rsi: float, macd: dict, z_score: float) -> str:
        """
        Votes across RSI, MACD, and Z-Score to produce UP / DOWN / NEUTRAL.
        Requires 2-of-3 agreement.
        Sensitized to (45/55) RSI and (1.0) Z-Score for higher reactivity.
        """
        votes_up = 0
        votes_down = 0

        # RSI: <45 → bullish reversal bias, >55 → bearish reversal bias
        if rsi > 0:
            if rsi < 45:
                votes_up += 1
            elif rsi > 55:
                votes_down += 1

        # MACD: positive histogram → upward momentum
        if macd['histogram'] > 0:
            votes_up += 1
        elif macd['histogram'] < 0:
            votes_down += 1

        # Z-Score: negative (below mean) → mean-reversion up
        if z_score < -1.0:
            votes_up += 1
        elif z_score > 1.0:
            votes_down += 1
            votes_down += 1

        if votes_up >= 2:
            return "UP"
        elif votes_down >= 2:
            return "DOWN"
        return "NEUTRAL"

    # ── EV ────────────────────────────────────────────────────────────────────
    def calculate_ev(self, p_win: float, pot_profit: float, pot_loss: float) -> float:
        return (p_win * pot_profit) - ((1.0 - p_win) * pot_loss)

    # ── Orderbook ─────────────────────────────────────────────────────────────
    def update_orderbook(self, side: str, price: float, volume: float):
        """Snapshot-style set (replaces bucket)."""
        book = self.bids if side == 'bid' else self.asks
        bp = round(round(price / ORDERBOOK_PRICE_BUCKET_SIZE) * ORDERBOOK_PRICE_BUCKET_SIZE, 4)
        if volume <= 0:
            book.pop(bp, None)
        else:
            book[bp] = volume

    def update_cvd(self, side: str, volume: float):
        """
        Updates Cumulative Volume Delta.
        Buy trade (taker hit Ask) = positive delta.
        Sell trade (taker hit Bid) = negative delta.
        """
        if side.lower() in ('buy', 'take'):
            self.cvd += volume
        elif side.lower() in ('sell', 'bid', 'give'):
            self.cvd -= volume
        
        # Periodic decay or cap could be added here if it drifts too much,
        # but pure CVD is usually preferred for session-based trading.
        self.cvd = np.clip(self.cvd, -1_000_000, 1_000_000)

    def update_snapshots(self, current_price: float):
        """Append price/cvd to history. Called once per second."""
        self.price_history.append(current_price)
        self.cvd_history.append(self.cvd)

    def update_oi(self, oi: float):
        self.oi_history.append(oi)

    def get_active_anomalies(self) -> dict:
        """
        Returns {'alerts': list, 'metrics': dict}
        """
        alerts = []
        metrics = {
            'price_delta_15m': 0.0,
            'cvd_delta_15m': 0.0,
            'price_delta_60m': 0.0,
            'cvd_delta_60m': 0.0
        }
        
        hist_len = len(self.cvd_history)
        if hist_len < 30:
            return {'alerts': alerts, 'metrics': metrics}

        # --- 15 Minute Window ---
        idx_15m = min(hist_len, 900)
        p_15m = self.price_history[-1] - self.price_history[-idx_15m]
        c_15m = self.cvd_history[-1] - self.cvd_history[-idx_15m]
        metrics['price_delta_15m'] = p_15m
        metrics['cvd_delta_15m'] = c_15m
        metrics['idx_15m'] = idx_15m

        # 15m Bearish Divergence
        if p_15m >= 15 and c_15m <= -5:
            alerts.append({
                "alert": "15m Bearish CVD Divergence",
                "explanation": f"Price rose ${p_15m:.1f} in 15m, but CVD dropped {abs(c_15m):.1f} BTC. Sellers absorbing limit orders."
            })
        
        # 15m Bullish Divergence
        if p_15m <= -15 and c_15m >= 5:
            alerts.append({
                "alert": "15m Bullish CVD Divergence",
                "explanation": f"Price fell ${abs(p_15m):.1f} in 15m, but CVD rose {c_15m:.1f} BTC. Major accumulation detected."
            })

        # --- 60 Minute Window (Coiled Spring) ---
        idx_60m = min(hist_len, 3600)
        p_60m = self.price_history[-1] - self.price_history[-idx_60m]
        c_60m = self.cvd_history[-1] - self.cvd_history[-idx_60m]
        metrics['price_delta_60m'] = p_60m
        metrics['cvd_delta_60m'] = c_60m
        metrics['idx_60m'] = idx_60m

        # 60m Major Divergence
        if p_60m > 50 and c_60m < -20:
            alerts.append({
                "alert": "COILED SPRING: 1H Bearish Divergence",
                "explanation": f"MASSIVE 1H Divergence: Price +${p_60m:.1f} | CVD {c_60m:.1f} BTC. Institutional exit in progress."
            })
        elif p_60m < -50 and c_60m > 20:
            alerts.append({
                "alert": "COILED SPRING: 1H Bullish Divergence",
                "explanation": f"MASSIVE 1H Divergence: Price -${abs(p_60m):.1f} | CVD +{c_60m:.1f} BTC. Multi-candle bottom forming."
            })

        # --- OI Spike Check (Rolling 15m Window) ---
        oi_len = len(self.oi_history)
        if oi_len >= 2:
            # Use a rolling 15-minute delta (approx 30 snapshots @ 30s intervals)
            idx_15m = min(oi_len, 30)
            oi_delta = self.oi_history[-1] - self.oi_history[-idx_15m]
            metrics['oi_delta_15m'] = oi_delta
            
            if abs(oi_delta) > 5:
                # Determine directional bias based on price move over same window
                p_move = metrics['price_delta_15m']
                
                bias = "NEUTRAL"
                if oi_delta < -5: # OI dropping = Liquidation/Flush
                    bias = "BEARISH (Long Liquidation)" if p_move < 0 else "BULLISH (Short Squeeze)"
                elif oi_delta > 5: # OI rising = Position Building
                    bias = "BEARISH (Short Building)" if p_move < 0 else "BULLISH (Long Building)"

                alerts.append({
                    "alert": f"Leverage {'Buildup' if oi_delta > 0 else 'Flush'} ({bias})",
                    "explanation": f"Open Interest shifted by {oi_delta:+.1f} BTC (15m). Expect a {bias} wick resolved soon."
                })

        return {'alerts': alerts, 'metrics': metrics}

    def delta_orderbook(self, side: str, price: float, delta: float):
        """Delta-style accumulate onto bucket."""
        book = self.bids if side == 'bid' else self.asks
        bp = round(round(price / ORDERBOOK_PRICE_BUCKET_SIZE) * ORDERBOOK_PRICE_BUCKET_SIZE, 4)
        new_vol = book.get(bp, 0.0) + delta
        if new_vol <= 0:
            book.pop(bp, None)
        else:
            book[bp] = new_vol

    def get_support_resistance_walls(self):
        supports = sorted([(p, v) for p, v in self.bids.items() if v >= MIN_WALL_VOLUME],
                          key=lambda x: x[0], reverse=True)
        resistances = sorted([(p, v) for p, v in self.asks.items() if v >= MIN_WALL_VOLUME],
                             key=lambda x: x[0])
        return supports, resistances

    # ── Master Signal Aggregator ──────────────────────────────────────────────
    def evaluate_signals(self, current_price: float, p_win_estimate: float,
                         pot_profit: float, pot_loss: float) -> dict:
        atr = self.calculate_atr()
        z_score = self.calculate_z_score(current_price)
        rsi = self.calculate_rsi()
        macd = self.calculate_macd()
        ev = self.calculate_ev(p_win_estimate, pot_profit, pot_loss)
        signal_direction = self.get_signal_direction(rsi, macd, z_score)
        supports, resistances = self.get_support_resistance_walls()

        # Signal Fusion (Smart Logic)
        # 1. Base Confluence: Direction must match CVD bias
        # If UP, CVD should be positive (Net Takers Buying)
        # If DOWN, CVD should be negative (Net Takers Selling)
        cvd_bias = "UP" if self.cvd > 0 else "DOWN"
        
        conviction_score = 0
        if signal_direction != "NEUTRAL":
            conviction_score += 40 # Base for having a direction
            if signal_direction == cvd_bias:
                conviction_score += 40 # Confluence Bonus!
            
            # Additional bonus for MACD agreement
            if (signal_direction == "UP" and macd['histogram'] > 0) or \
               (signal_direction == "DOWN" and macd['histogram'] < 0):
                conviction_score += 20

        is_good_setup = (
            conviction_score >= 80 and
            abs(z_score) >= Z_SCORE_THRESHOLD and
            ev > EV_THRESHOLD
        )

        return {
            'atr': atr,
            'z_score': z_score,
            'rsi': rsi,
            'macd': macd,
            'cvd': self.cvd,
            'signal_direction': signal_direction,
            'conviction': conviction_score,
            'ev': ev,
            'supports': supports,
            'resistances': resistances,
            'is_good_setup': is_good_setup
        }
