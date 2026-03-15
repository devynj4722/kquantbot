import pandas as pd
import numpy as np
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

    def add_kline(self, kline_data):
        """Adds OHLCV candle dict. Keeps buffer bounded."""
        self.klines.append(kline_data)
        max_len = max(ATR_PERIODS, RSI_PERIOD, MACD_SLOW + MACD_SIGNAL) * 3
        if len(self.klines) > max_len:
            self.klines.pop(0)

    def _close_series(self) -> pd.Series:
        return pd.DataFrame(self.klines)['close']

    # ── ATR ───────────────────────────────────────────────────────────────────
    def calculate_atr(self) -> float:
        if len(self.klines) < ATR_PERIODS + 1:
            return 0.0
        df = pd.DataFrame(self.klines)
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
        """
        votes_up = 0
        votes_down = 0

        # RSI: <40 → bullish reversal, >60 → bearish reversal
        if rsi > 0:
            if rsi < 40:
                votes_up += 1
            elif rsi > 60:
                votes_down += 1

        # MACD: positive histogram → upward momentum
        if macd['histogram'] > 0:
            votes_up += 1
        elif macd['histogram'] < 0:
            votes_down += 1

        # Z-Score: negative (below mean) → mean-reversion up
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

        is_good_setup = (
            abs(z_score) >= Z_SCORE_THRESHOLD and
            ev > EV_THRESHOLD and
            signal_direction != "NEUTRAL"
        )

        return {
            'atr': atr,
            'z_score': z_score,
            'rsi': rsi,
            'macd': macd,
            'signal_direction': signal_direction,
            'ev': ev,
            'supports': supports,
            'resistances': resistances,
            'is_good_setup': is_good_setup
        }
