import pandas as pd
import numpy as np
import math
from collections import deque
from typing import List
from config import (
    ATR_PERIODS, Z_SCORE_THRESHOLD, EV_THRESHOLD, MIN_WALL_VOLUME, ORDERBOOK_PRICE_BUCKET_SIZE,
    RSI_OB_THRESHOLD, RSI_OS_THRESHOLD, RSI_SIGNAL_UP, RSI_SIGNAL_DOWN,
    ATR_DIST_KILL_SWITCH, OI_PCT_THRESHOLD, OI_15M_SAMPLES, PRICE_15M_SAMPLES
)

RSI_PERIOD = 14
MACD_FAST = 5    # 5-min fast EMA — tuned for 15m binary window
MACD_SLOW  = 10  # 10-min slow EMA — tuned for 15m binary window
MACD_SIGNAL = 3  # 3-bar signal smoothing — reacts within same 15m window


class MathEngine:
    def __init__(self):
        self.klines = []
        self.bids = {}
        self.asks = {}
        self.cvd = 0.0  # Cumulative Volume Delta
        self.cvd_history = deque(maxlen=3600)   # 1-second snapshots (60 minutes)
        self.oi_history = deque(maxlen=120)    # 30-second snaphots (60 minutes)
        self.price_history = deque(maxlen=3600) # 1-second snapshots (60 minutes)
        self.macd_history = deque(maxlen=10)    # For KCI timing (last few histogram values)

    def add_kline(self, kline_data):
        """Adds OHLCV candle dict. Keeps buffer bounded."""
        kline_data['cvd'] = self.cvd # Snapshot CVD at candle close
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
    def calculate_atr(self, window: int = ATR_PERIODS) -> float:
        if len(self.klines) < window + 1:
            return 0.0
        df = pd.DataFrame(self.klines)
        if 'close' not in df.columns or 'high' not in df.columns or 'low' not in df.columns:
            return 0.0
        df['prev_close'] = df['close'].shift(1)
        df['tr'] = df[['high', 'prev_close']].max(axis=1) - df[['low', 'prev_close']].min(axis=1)
        atr = df['tr'].rolling(window=window).mean().iloc[-1]
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
    def get_signal_direction(self, rsi: float, macd: dict, z_score: float,
                              macd_history=None) -> str:
        """
        Votes across RSI, MACD Slope, and Z-Score to produce UP / DOWN / NEUTRAL.
        Requires 2-of-3 agreement.

        MACD uses histogram SLOPE (rising/falling), not absolute sign.
        This is forward-looking vs the lagging sign-only approach.

        Z-Score threshold: ±1.5 (balanced between direction sensitivity ±1.0
        and exhaustion confirmation ±2.0).
        """
        votes_up = 0
        votes_down = 0

        # RSI: below 45 → oversold bias → UP; above 55 → overbought bias → DOWN
        if rsi > 0:
            if rsi < RSI_SIGNAL_UP:
                votes_up += 1
            elif rsi > RSI_SIGNAL_DOWN:
                votes_down += 1

        # MACD Slope: rising histogram = fading bearish momentum = UP edge
        #             falling histogram = fading bullish momentum = DOWN edge
        # This is LEADING vs the lagging positive/negative sign.
        if macd_history and len(macd_history) >= 2:
            hist_slope = macd_history[-1] - macd_history[-2]
            if hist_slope > 0:
                votes_up += 1
            elif hist_slope < 0:
                votes_down += 1
        else:
            # Fallback to sign if no history yet
            if macd['histogram'] > 0:
                votes_up += 1
            elif macd['histogram'] < 0:
                votes_down += 1

        # Z-Score: ±1.5 balances sensitivity vs exhaustion engine's ±2.0 requirement
        if z_score < -1.5:
            votes_up += 1
        elif z_score > 1.5:
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

    def _calculate_slope(self, data: List[float]) -> float:
        if len(data) < 2: return 0.0
        x = np.arange(len(data))
        y = np.array(data)
        slope, _ = np.polyfit(x, y, 1)
        return float(slope)

    def _get_resampled_data(self, key: str, points: int, interval: int) -> List[float]:
        """ Extracts legacy points from klines list for specific key (e.g. 'high' or 'cvd') """
        if len(self.klines) < 2: return []
        # Get specified number of points, spaced by interval
        data = []
        for i in range(points):
            idx = -(1 + i * interval)
            if abs(idx) <= len(self.klines):
                data.append(self.klines[idx].get(key, 0.0))
            else:
                break
        data.reverse() # Oldest to Newest
        return data

    def get_active_anomalies(self) -> dict:
        """
        Returns {'alerts': list, 'metrics': dict}
        Uses Dynamic ATR Thresholds and Linear Regression Slopes.
        """
        alerts = []
        metrics = {}
        
        atr14 = self.calculate_atr(14)
        atr60 = self.calculate_atr(60)

        # --- 1. 15m Divergence (Last 4 Candles) ---
        if len(self.klines) >= 4 and atr14 > 0:
            # Linear Regression on Price (Highs) and CVD
            p_recent = [k['high'] for k in self.klines[-4:]]
            c_recent = [k['cvd'] for k in self.klines[-4:]]
            
            p_slope = self._calculate_slope(p_recent)
            c_slope = self._calculate_slope(c_recent)
            metrics['c_slope_15m'] = c_slope
            p_delta = self.klines[-1]['close'] - self.klines[-4]['open']
            
            if p_slope > 0 and c_slope < 0 and p_delta >= atr14:
                alerts.append({
                    "alert": "15m Bearish CVD Divergence",
                    "explanation": f"Price Slope +{p_slope:.2f} | CVD Slope {c_slope:.2f}. Institutional distribution detected above {1.0} ATR."
                })
            elif p_slope < 0 and c_slope > 0 and p_delta <= -atr14:
                alerts.append({
                    "alert": "15m Bullish CVD Divergence",
                    "explanation": f"Price Slope {p_slope:.2f} | CVD Slope +{c_slope:.2f}. Institutional accumulation detected below {1.0} ATR."
                })

        # --- 2. 1H Context (Resampled 4 points over 60m) ---
        if len(self.klines) >= 60 and atr60 > 0:
            p_1h = self._get_resampled_data('close', 4, 15)
            c_1h = self._get_resampled_data('cvd', 4, 15)
            
            p_slope_1h = self._calculate_slope(p_1h)
            c_slope_1h = self._calculate_slope(c_1h)
            p_delta_1h = p_1h[-1] - p_1h[0]
            
            if p_slope_1h > 0 and c_slope_1h < 0 and p_delta_1h >= atr60:
                alerts.append({
                    "alert": "COILED SPRING: 1H Bearish Divergence",
                    "explanation": f"1H Price Slope +{p_slope_1h:.2f} | CVD Slope {c_slope_1h:.2f}. Macro institutional exit in progress."
                })
            elif p_slope_1h < 0 and c_slope_1h > 0 and p_delta_1h <= -atr60:
                alerts.append({
                    "alert": "COILED SPRING: 1H Bullish Divergence",
                    "explanation": f"1H Price Slope {p_slope_1h:.2f} | CVD Slope +{c_slope_1h:.2f}. Macro accumulation forming bottom."
                })

        # --- 3. Open Interest (% Change over 15m) ---
        oi_len = len(self.oi_history)
        if oi_len >= OI_15M_SAMPLES: # 15 mins
            oi_start = self.oi_history[-OI_15M_SAMPLES]
            oi_end = self.oi_history[-1]
            if oi_start > 0:
                oi_pct = (oi_end - oi_start) / oi_start
                metrics['oi_pct_15m'] = oi_pct
                
                if abs(oi_pct) > OI_PCT_THRESHOLD: # % Threshold
                    # Determine directional bias based on price move over same window
                    p_move = 0
                    if len(self.price_history) >= PRICE_15M_SAMPLES:
                        p_move = self.price_history[-1] - self.price_history[-PRICE_15M_SAMPLES]
                    
                    bias = "NEUTRAL"
                    if oi_pct < -OI_PCT_THRESHOLD: # Flush
                        bias = "BEARISH (Long Liquidation)" if p_move < 0 else "BULLISH (Short Squeeze)"
                    else: # Buildup
                        bias = "BEARISH (Short Building)" if p_move < 0 else "BULLISH (Long Building)"

                    alerts.append({
                        "alert": f"Leverage {'Buildup' if oi_pct > 0 else 'Flush'} ({bias})",
                        "explanation": f"Open Interest shifted by {oi_pct:+.1%}. Volatility 'coiled spring' active."
                    })

        # --- Metrics for GUI Display ---
        metrics['price_delta_15m'] = self.klines[-1]['close'] - self.klines[-idx_15m]['open'] if (idx_15m := min(len(self.klines), 15)) >= 1 else 0
        metrics['cvd_delta_15m'] = self.cvd - self.klines[-idx_15m]['cvd'] if idx_15m >= 1 else 0
        metrics['price_delta_60m'] = self.klines[-1]['close'] - self.klines[-idx_60m]['open'] if (idx_60m := min(len(self.klines), 60)) >= 1 else 0
        metrics['cvd_delta_60m'] = self.cvd - self.klines[-idx_60m]['cvd'] if idx_60m >= 1 else 0
        metrics['idx_15m'] = idx_15m
        metrics['idx_60m'] = idx_60m

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
    # ── Signal Aggregator (KCI) ────────────────────────────────────────────────
    def evaluate_signals(self, current_price: float, p_win_estimate: float,
                         pot_profit: float, pot_loss: float,
                         strike_price: float = 0.0,
                         time_left: int = 900) -> dict:
        atr = self.calculate_atr()
        z_score = self.calculate_z_score(current_price)
        rsi = self.calculate_rsi()
        macd = self.calculate_macd()
        ev = self.calculate_ev(p_win_estimate, pot_profit, pot_loss)
        # Append MACD history BEFORE direction call so slope is always computable
        self.macd_history.append(macd['histogram'])
        signal_direction = self.get_signal_direction(rsi, macd, z_score,
                                                     macd_history=self.macd_history)
        supports, resistances = self.get_support_resistance_walls()
        anomalies = self.get_active_anomalies()

        # --- Phase 1: Kill Switches (K) ---
        # 1. Reachability — time-adjusted: near expiry, tighten the allowed ATR distance
        atr_dist = 0.0
        if atr > 0 and strike_price > 0:
            atr_dist = (current_price - strike_price) / atr
        # Within last 5 min, require strike to be within 1.0 ATR (< 2.0 ATR otherwise)
        time_atr_limit = ATR_DIST_KILL_SWITCH if time_left > 300 else 1.0
        k_atr = 1 if abs(atr_dist) < time_atr_limit else 0
        
        # 2. Risk
        k_ev = 1 if ev > EV_THRESHOLD else 0
        
        # 3. The Clock — tightened to :57-:05 (was :55-:10), frees 24% more entry time
        from datetime import datetime
        now_min = datetime.now().minute
        k_time = 0 if (now_min >= 57 or now_min <= 5) else 1
        
        # --- Phase 2: Weighted Conviction Score (W) ---
        # 1. Exhaustion Engine (Max 30)
        w_z = 0
        abs_z = abs(z_score)
        if abs_z >= Z_SCORE_THRESHOLD:
            if rsi >= RSI_OB_THRESHOLD or rsi <= RSI_OS_THRESHOLD: 
                w_z = 30
            else:
                w_z = 25
        elif abs_z >= 1.2:
            w_z = 15
        
        # 2. Truth Engine (Max 30) — CVD Support & Anomalies
        w_cvd = 0
        mapping = {"UP": "BULLISH", "DOWN": "BEARISH"}
        target_anom = mapping.get(signal_direction, "NONE")
        has_anom = any(target_anom in a['alert'].upper() for a in anomalies.get('alerts', []))
        if has_anom:
            w_cvd = 30
        else:
            # Reward healthy trend agreement instead of just anomalies
            cvd_delta = anomalies.get('metrics', {}).get('cvd_delta_15m', 0)
            if signal_direction == "UP" and cvd_delta > 0:
                w_cvd = int(min(20, (cvd_delta / 5.0) * 20))
            elif signal_direction == "DOWN" and cvd_delta < 0:
                w_cvd = int(min(20, (abs(cvd_delta) / 5.0) * 20))
            
        # 3. Timing Engine (Max 40) — Normalized MACD Shift
        w_macd = 0
        if len(self.macd_history) >= 2 and atr > 0:
            hist_shift = self.macd_history[-1] - self.macd_history[-2]  # positive = histogram rising
            normalized_shift = abs(hist_shift) / atr
            if (signal_direction == "UP" and hist_shift > 0) or \
               (signal_direction == "DOWN" and hist_shift < 0):
                # Scale 10 -> 40 based on normalized shift momentum
                w_macd = int(min(40, 10 + (normalized_shift * 100)))

        # --- Master Equation ---
        k_factor = (k_atr * k_ev * k_time)
        w_sum = (w_z + w_cvd + w_macd)
        
        # Display Potency (W-score) as the primary KCI score for UI transparency
        kci = float(w_sum) 
        
        # A "Good Setup" MUST pass all Kill Switches AND have high potency
        is_good_setup = (kci >= 50 and k_factor == 1)

        return {
            'atr': atr,
            'z_score': z_score,
            'rsi': rsi,
            'macd': macd,
            'cvd': self.cvd,
            'signal_direction': signal_direction,
            'ev': ev,
            'kci': kci,
            'conviction': w_sum, # Legacy key for UI banner
            'k_factor': k_factor,
            'w_sum': w_sum,
            'k_atr': k_atr,
            'k_ev': k_ev,
            'k_time': k_time,
            'atr_distance': atr_dist,
            'strike_price': strike_price,
            'supports': supports,
            'resistances': resistances,
            'is_good_setup': is_good_setup,
            'anomalies': anomalies
        }
