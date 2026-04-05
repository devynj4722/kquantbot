"""
edge_engine.py
Weighted composite scoring engine for mispriced contract detection.
Combines edge, momentum, orderbook, CVD, basis, and regime signals
into a single composite score. Replaces KCI as the primary trade gate.

Architecture:
  1. Each indicator produces a component score (0-100)
  2. Components are weighted and summed into a composite (0-100)
  3. Kill switches (hard gates) can block a trade regardless of score
  4. Smart sizing scales position based on edge + context

Signal Flow:
  math_engine (raw indicators) → edge_engine (scoring + decision) → trade_executor
"""
import math
from config import (
    TRADE_SIZE_DOLLARS,
    Z_SCORE_THRESHOLD, RSI_OB_THRESHOLD, RSI_OS_THRESHOLD,
    RSI_SIGNAL_UP, RSI_SIGNAL_DOWN, ATR_DIST_KILL_SWITCH,
    MIN_EDGE_CENTS, STRONG_EDGE_CENTS,
    IMBALANCE_DEPTH_CENTS, IMBALANCE_STRONG,
    REGIME_SQUEEZE_RATIO, REGIME_EXPANSION_RATIO,
    BASIS_MIN_DIVERGENCE,
    W_EDGE, W_MOMENTUM, W_ORDERBOOK, W_CVD, W_BASIS, W_REGIME,
    MIN_COMPOSITE_SCORE
)


class EdgeEngine:
    """Scores trade setups by combining multiple independent signals."""

    def __init__(self, math_engine):
        self.math = math_engine

    # ── 1. Edge Detection ────────────────────────────────────────────────────
    def calculate_edge(self, model_p_win: float, market_p_win: float) -> dict:
        """
        Core mispricing detector.  Compares our model probability (sigmoid of
        Z-score) against the Kalshi market-implied probability (1 - best NO ask).

        Returns edge in probability units (0-1) and cents (0-100).
        Positive edge → YES is underpriced.  Negative → NO is underpriced.
        """
        edge = model_p_win - market_p_win
        edge_cents = round(abs(edge) * 100, 1)

        if edge > 0.005:
            edge_direction = "YES_UNDERPRICED"
        elif edge < -0.005:
            edge_direction = "NO_UNDERPRICED"
        else:
            edge_direction = "FAIR"

        return {
            "edge": round(edge, 4),
            "edge_cents": edge_cents,
            "edge_direction": edge_direction,
            "model_p_win": round(model_p_win, 4),
            "market_p_win": round(market_p_win, 4),
        }

    # ── 2. Orderbook Imbalance ───────────────────────────────────────────────
    def calculate_orderbook_imbalance(self) -> dict:
        """
        Sums bid vs ask volume within IMBALANCE_DEPTH_CENTS of the best price.
        Thin Kalshi books make even small imbalances meaningful.

        ratio > 1 → bid-heavy (YES pressure)
        ratio < 1 → ask-heavy (NO pressure)
        """
        bids = self.math.bids
        asks = self.math.asks

        if not bids or not asks:
            return {"imbalance_ratio": 1.0, "imbalance_direction": "NEUTRAL",
                    "bid_volume": 0.0, "ask_volume": 0.0}

        best_bid = max(bids.keys())
        best_ask = min(asks.keys())

        bid_vol = sum(v for p, v in bids.items()
                      if p >= best_bid - IMBALANCE_DEPTH_CENTS)
        ask_vol = sum(v for p, v in asks.items()
                      if p <= best_ask + IMBALANCE_DEPTH_CENTS)

        if ask_vol <= 0:
            ratio = 10.0 if bid_vol > 0 else 1.0
        else:
            ratio = bid_vol / ask_vol

        if ratio >= 1.5:
            direction = "YES_PRESSURE"
        elif ratio <= 0.67:
            direction = "NO_PRESSURE"
        else:
            direction = "NEUTRAL"

        return {
            "imbalance_ratio": round(ratio, 2),
            "imbalance_direction": direction,
            "bid_volume": round(bid_vol, 1),
            "ask_volume": round(ask_vol, 1),
        }

    # ── 3. Regime Detection ──────────────────────────────────────────────────
    def detect_regime(self) -> dict:
        """
        Classifies market regime from short/long ATR ratio + RSI state.

        SQUEEZE   (vol_ratio < 0.7)  → mean reversion or breakout imminent
        EXPANSION (vol_ratio > 1.3)  → ride momentum
        TRENDING  (RSI outside 40-60) → follow the trend
        CHOPPY    (RSI 40-60, normal vol) → stay flat
        """
        import pandas as pd

        klines = self.math.klines
        if len(klines) < 20:
            return {"regime": "UNKNOWN", "strategy": "WAIT",
                    "vol_ratio": 0.0, "regime_strength": 0}

        df = pd.DataFrame(klines)
        if 'close' not in df.columns or 'high' not in df.columns:
            return {"regime": "UNKNOWN", "strategy": "WAIT",
                    "vol_ratio": 0.0, "regime_strength": 0}

        df['prev_close'] = df['close'].shift(1)
        df['tr'] = (df[['high', 'prev_close']].max(axis=1)
                    - df[['low', 'prev_close']].min(axis=1))

        atr_short = df['tr'].rolling(5).mean().iloc[-1]
        atr_long = df['tr'].rolling(min(20, len(df))).mean().iloc[-1]

        if pd.isna(atr_short) or pd.isna(atr_long) or atr_long == 0:
            return {"regime": "UNKNOWN", "strategy": "WAIT",
                    "vol_ratio": 0.0, "regime_strength": 0}

        vol_ratio = atr_short / atr_long
        rsi = self.math.calculate_rsi()

        if vol_ratio < REGIME_SQUEEZE_RATIO:
            regime = "SQUEEZE"
            if rsi > 70 or rsi < 30:
                strategy, strength = "BREAKOUT_IMMINENT", 85
            else:
                strategy, strength = "MEAN_REVERSION", 70

        elif vol_ratio > REGIME_EXPANSION_RATIO:
            regime = "EXPANSION"
            if rsi > 60 or rsi < 40:
                strategy, strength = "MOMENTUM", 80
            else:
                strategy, strength = "MOMENTUM_FADING", 50

        else:
            if 40 < rsi < 60:
                regime, strategy, strength = "CHOPPY", "AVOID", 20
            else:
                regime, strategy, strength = "TRENDING", "MOMENTUM", 65

        return {
            "regime": regime,
            "strategy": strategy,
            "vol_ratio": round(vol_ratio, 3),
            "regime_strength": strength,
        }

    # ── 4. Basis Arbitrage ───────────────────────────────────────────────────
    def calculate_basis_signal(self, model_p_win: float,
                               market_p_win: float) -> dict:
        """
        Detects Kalshi lag vs Coinbase spot.  When our spot-momentum model
        diverges from the Kalshi market price by > BASIS_MIN_DIVERGENCE,
        there is a convergence trade available.
        """
        divergence = model_p_win - market_p_win
        abs_div = abs(divergence)

        if abs_div < BASIS_MIN_DIVERGENCE:
            return {"basis_signal": "NONE", "basis_divergence": round(divergence, 4),
                    "basis_strength": 0}

        signal = "BUY_YES" if divergence > 0 else "BUY_NO"
        strength = min(100, int((abs_div - BASIS_MIN_DIVERGENCE) / 0.17 * 70 + 30))

        return {
            "basis_signal": signal,
            "basis_divergence": round(divergence, 4),
            "basis_strength": strength,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Component Scorers (each returns 0-100)
    # ══════════════════════════════════════════════════════════════════════════

    def _score_edge(self, edge_cents: float) -> float:
        if edge_cents < 5:
            return 0
        if edge_cents < 8:
            return 20 + (edge_cents - 5) / 3 * 20
        if edge_cents < 15:
            return 40 + (edge_cents - 8) / 7 * 30
        if edge_cents < 25:
            return 70 + (edge_cents - 15) / 10 * 20
        return min(100, 90 + (edge_cents - 25) / 10 * 10)

    def _score_momentum(self, rsi: float, macd_hist: float,
                        z_score: float, direction: str) -> float:
        votes = 0
        if direction == "UP":
            if rsi < RSI_SIGNAL_UP:   votes += 1
            if macd_hist > 0:         votes += 1
            if z_score < -1.5:        votes += 1
        elif direction == "DOWN":
            if rsi > RSI_SIGNAL_DOWN: votes += 1
            if macd_hist < 0:         votes += 1
            if z_score > 1.5:         votes += 1

        score = {3: 80, 2: 50, 1: 20}.get(votes, 0)

        if rsi >= RSI_OB_THRESHOLD or rsi <= RSI_OS_THRESHOLD:
            score = min(100, score + 20)
        return score

    def _score_orderbook(self, imbalance: dict, direction: str) -> float:
        ratio = imbalance["imbalance_ratio"]
        ob_dir = imbalance["imbalance_direction"]

        aligned = (
            (direction == "UP"   and ob_dir == "YES_PRESSURE") or
            (direction == "DOWN" and ob_dir == "NO_PRESSURE")
        )
        counter = (
            (direction == "UP"   and ob_dir == "NO_PRESSURE") or
            (direction == "DOWN" and ob_dir == "YES_PRESSURE")
        )

        if counter:
            return max(0, 20 - (max(ratio, 1 / ratio) - 1.5) * 20)

        if aligned:
            eff = ratio if direction == "UP" else (1.0 / ratio if ratio > 0 else 1.0)
            if eff >= IMBALANCE_STRONG:
                return 90
            if eff >= 2.0:
                return 70
            if eff >= 1.5:
                return 45
            return 25

        return 30  # NEUTRAL

    def _score_cvd(self, cvd_delta: float, direction: str,
                   has_divergence: bool) -> float:
        if has_divergence:
            return 95

        if direction == "UP" and cvd_delta > 0:
            return min(80, 30 + abs(cvd_delta) / 5.0 * 50)
        if direction == "DOWN" and cvd_delta < 0:
            return min(80, 30 + abs(cvd_delta) / 5.0 * 50)

        # CVD is against our direction
        if (direction == "UP" and cvd_delta < -2) or \
           (direction == "DOWN" and cvd_delta > 2):
            return 10

        return 25  # Neutral

    def _score_basis(self, basis: dict, direction: str) -> float:
        if basis["basis_signal"] == "NONE":
            return 30

        aligned = (
            (direction == "UP"   and basis["basis_signal"] == "BUY_YES") or
            (direction == "DOWN" and basis["basis_signal"] == "BUY_NO")
        )
        if aligned:
            return basis["basis_strength"]
        return max(0, 30 - basis["basis_strength"] * 0.3)

    def _score_regime(self, regime: dict) -> float:
        r = regime["regime"]
        strat = regime["strategy"]
        if r == "CHOPPY" and strat == "AVOID":
            return 15
        if strat in ("MOMENTUM", "BREAKOUT_IMMINENT", "MEAN_REVERSION"):
            return regime["regime_strength"]
        if strat == "MOMENTUM_FADING":
            return 35
        return 30

    # ── 4b. CVD Confirm / Fade Filter ────────────────────────────────────────
    def calculate_cvd_confirmation(self, direction: str, cvd_delta_15m: float,
                                   cvd_delta_60m: float) -> dict:
        """
        Uses CVD as a hard confirm/fade filter on top of the weighted score.

        CONFIRM: CVD agrees with price direction → trade is real
        FADE:    CVD diverges from price → likely a trap / distribution
        NEUTRAL: Insufficient data or weak signal
        """
        if direction == "NEUTRAL":
            return {"cvd_verdict": "NEUTRAL", "cvd_confirm_score": 0,
                    "explanation": "No direction to confirm"}

        # 15m is the primary window; 60m is context
        if direction == "UP":
            aligned_15 = cvd_delta_15m > 0
            strong_15  = cvd_delta_15m > 2.0
            fade_15    = cvd_delta_15m < -1.5
            aligned_60 = cvd_delta_60m > 0
        else:  # DOWN
            aligned_15 = cvd_delta_15m < 0
            strong_15  = cvd_delta_15m < -2.0
            fade_15    = cvd_delta_15m > 1.5
            aligned_60 = cvd_delta_60m < 0

        # Strong confirmation: both timeframes agree
        if strong_15 and aligned_60:
            return {"cvd_verdict": "STRONG_CONFIRM", "cvd_confirm_score": 100,
                    "explanation": f"15m CVD {cvd_delta_15m:+.1f} + 60m CVD {cvd_delta_60m:+.1f} both aligned"}
        if aligned_15 and aligned_60:
            return {"cvd_verdict": "CONFIRM", "cvd_confirm_score": 70,
                    "explanation": f"Both timeframes support {direction}"}
        if aligned_15 and not aligned_60:
            return {"cvd_verdict": "WEAK_CONFIRM", "cvd_confirm_score": 45,
                    "explanation": f"15m confirms but 60m diverges"}

        # Fade: CVD is actively against the direction
        if fade_15:
            return {"cvd_verdict": "FADE", "cvd_confirm_score": -30,
                    "explanation": f"CVD strongly opposes {direction} — likely a trap"}

        return {"cvd_verdict": "NEUTRAL", "cvd_confirm_score": 20,
                "explanation": "CVD inconclusive"}

    # ── 4c. Time Decay Momentum ──────────────────────────────────────────────
    def calculate_time_decay_adjustments(self, time_left: int,
                                         regime: dict) -> dict:
        """
        Adjusts signal weights and strategy based on how much time remains.

        > 10 min:  Standard momentum — use normal weights
        5-10 min:  Prime window — full confidence in setups
        1-5 min:   Late window — start favoring mean reversion over momentum
        < 1 min:   Final minute — very conservative, fade extremes
        """
        if time_left > 600:
            phase = "EARLY"
            strategy_hint = "MOMENTUM"
            # Slightly reduce confidence — market is still forming
            weight_adj = {"momentum": 0.9, "mean_rev": 1.0, "confidence": 0.9}
        elif time_left > 300:
            phase = "PRIME"
            strategy_hint = "MOMENTUM"
            # Best window — full confidence
            weight_adj = {"momentum": 1.0, "mean_rev": 1.0, "confidence": 1.0}
        elif time_left > 60:
            phase = "LATE"
            strategy_hint = "MEAN_REVERSION"
            # Start fading momentum, boost reversion signals
            weight_adj = {"momentum": 0.6, "mean_rev": 1.4, "confidence": 0.85}
        else:
            phase = "FINAL_MINUTE"
            strategy_hint = "SCALP_ONLY"
            # Very conservative — prices often whip in final 60s
            weight_adj = {"momentum": 0.3, "mean_rev": 1.2, "confidence": 0.5}

        # Regime interaction: if we're in SQUEEZE during LATE phase, breakout becomes more likely
        if phase == "LATE" and regime.get("regime") == "SQUEEZE":
            strategy_hint = "LATE_SQUEEZE_BREAKOUT"
            weight_adj["confidence"] = 1.1  # Actually higher confidence here

        return {
            "phase": phase,
            "strategy_hint": strategy_hint,
            "weight_adj": weight_adj,
        }

    # ── 4d. Portfolio Hedging ────────────────────────────────────────────────
    def calculate_hedge_factor(self, pending_positions: list) -> dict:
        """
        Tracks net directional exposure from open/pending trades and reduces
        position size when too heavily biased in one direction.

        pending_positions: list of dicts with 'direction' and 'yes_price' keys
                          (from trade_logger.get_pending_tickers + read)
        """
        if not pending_positions:
            return {"net_exposure": "FLAT", "hedge_factor": 1.0,
                    "up_count": 0, "down_count": 0}

        up_count = sum(1 for p in pending_positions if p.get("direction") == "UP")
        down_count = sum(1 for p in pending_positions if p.get("direction") == "DOWN")
        total = up_count + down_count

        if total == 0:
            return {"net_exposure": "FLAT", "hedge_factor": 1.0,
                    "up_count": 0, "down_count": 0}

        imbalance = abs(up_count - down_count)

        if imbalance == 0:
            exposure = "BALANCED"
            hedge_factor = 1.0
        elif imbalance == 1:
            exposure = "SLIGHT_" + ("LONG" if up_count > down_count else "SHORT")
            hedge_factor = 0.9
        elif imbalance == 2:
            exposure = "MODERATE_" + ("LONG" if up_count > down_count else "SHORT")
            hedge_factor = 0.7
        else:
            exposure = "HEAVY_" + ("LONG" if up_count > down_count else "SHORT")
            hedge_factor = 0.5

        return {
            "net_exposure": exposure,
            "hedge_factor": hedge_factor,
            "up_count": up_count,
            "down_count": down_count,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # 5. Composite Score — the master decision function
    # ══════════════════════════════════════════════════════════════════════════

    def calculate_composite_score(self, signals: dict, edge_data: dict,
                                  imbalance: dict, regime: dict,
                                  basis: dict, cvd_confirm: dict,
                                  time_decay: dict,
                                  hedge: dict) -> dict:
        """
        Weighted composite of all indicators, adjusted by time decay,
        CVD confirmation, and portfolio hedge factor.
        """
        direction = signals.get("signal_direction", "NEUTRAL")
        if direction == "NEUTRAL":
            return {"composite_score": 0, "should_trade": False,
                    "setup_type": "NONE", "gates": {}, "components": {},
                    "time_phase": "N/A", "cvd_verdict": "N/A",
                    "net_exposure": "N/A"}

        # ── Extract CVD context ──────────────────────────────────────────
        anomalies = signals.get("anomalies", {})
        cvd_delta = anomalies.get("metrics", {}).get("cvd_delta_15m", 0)
        tag = {"UP": "BULLISH", "DOWN": "BEARISH"}.get(direction, "")
        has_div = any(tag in a["alert"].upper()
                      for a in anomalies.get("alerts", []))

        # ── Component scores ─────────────────────────────────────────────
        s_edge = self._score_edge(edge_data["edge_cents"])
        s_mom  = self._score_momentum(
            signals.get("rsi", 50),
            signals.get("macd", {}).get("histogram", 0),
            signals.get("z_score", 0),
            direction,
        )
        s_ob   = self._score_orderbook(imbalance, direction)
        s_cvd  = self._score_cvd(cvd_delta, direction, has_div)
        s_bas  = self._score_basis(basis, direction)
        s_reg  = self._score_regime(regime)

        # ── Time Decay Adjustments ───────────────────────────────────────
        # Shift momentum vs mean-reversion weight based on time remaining
        td = time_decay.get("weight_adj", {})
        mom_adj = td.get("momentum", 1.0)
        confidence_adj = td.get("confidence", 1.0)

        # Apply time-decay modifier to momentum score
        s_mom = s_mom * mom_adj

        # In late phase, boost regime score if mean-reversion is recommended
        phase = time_decay.get("phase", "PRIME")
        if phase in ("LATE", "FINAL_MINUTE"):
            if regime.get("strategy") == "MEAN_REVERSION":
                s_reg = min(100, s_reg * td.get("mean_rev", 1.0))

        # ── CVD Confirm/Fade Modifier ────────────────────────────────────
        # Hard fade: if CVD says FADE, reduce composite significantly
        cvd_verdict = cvd_confirm.get("cvd_verdict", "NEUTRAL")
        cvd_adj = 1.0
        if cvd_verdict == "STRONG_CONFIRM":
            cvd_adj = 1.15  # Boost
        elif cvd_verdict == "CONFIRM":
            cvd_adj = 1.05
        elif cvd_verdict == "FADE":
            cvd_adj = 0.6   # Severe penalty — CVD says this is a trap
        elif cvd_verdict == "WEAK_CONFIRM":
            cvd_adj = 0.95

        # ── Weighted sum ─────────────────────────────────────────────────
        raw_composite = (
            s_edge * W_EDGE +
            s_mom  * W_MOMENTUM +
            s_ob   * W_ORDERBOOK +
            s_cvd  * W_CVD +
            s_bas  * W_BASIS +
            s_reg  * W_REGIME
        )

        # Apply modifiers: confidence (time), CVD confirm/fade, hedge factor
        hedge_factor = hedge.get("hedge_factor", 1.0)
        composite = round(raw_composite * confidence_adj * cvd_adj, 1)

        # ── Kill switches (hard gates) ───────────────────────────────────
        edge_pass = edge_data["edge_cents"] >= MIN_EDGE_CENTS

        from datetime import datetime
        now_min = datetime.now().minute
        time_pass = not (now_min >= 57 or now_min <= 5)

        atr_dist = signals.get("atr_distance", 0)
        time_left = signals.get("time_left", 900)
        atr_limit = ATR_DIST_KILL_SWITCH if time_left > 300 else 1.0
        atr_pass = (abs(atr_dist) < atr_limit
                    if signals.get("strike_price", 0) > 0 else True)

        ob_pass = s_ob >= 15
        cvd_pass = cvd_verdict != "FADE"  # Hard gate: CVD fade kills the trade

        # Final minute gate: only trade if score is very high
        final_min_pass = (phase != "FINAL_MINUTE" or composite >= 70)

        all_gates = (edge_pass and time_pass and atr_pass
                     and ob_pass and cvd_pass and final_min_pass)
        should_trade = composite >= MIN_COMPOSITE_SCORE and all_gates

        # ── Setup classification ─────────────────────────────────────────
        setup_type = self._classify_setup(
            s_edge, s_mom, s_ob, s_cvd, s_bas, s_reg,
            regime, has_div, edge_data,
        )

        # Override setup type for time-decay specific strategies
        if phase == "LATE" and should_trade:
            if regime.get("strategy") == "MEAN_REVERSION":
                setup_type = "LATE_MEAN_REVERSION"
            elif time_decay.get("strategy_hint") == "LATE_SQUEEZE_BREAKOUT":
                setup_type = "LATE_SQUEEZE_BREAKOUT"
        elif phase == "FINAL_MINUTE" and should_trade:
            setup_type = "FINAL_MINUTE_SCALP"

        return {
            "composite_score": composite,
            "should_trade": should_trade,
            "setup_type": setup_type,
            "time_phase": phase,
            "cvd_verdict": cvd_verdict,
            "net_exposure": hedge.get("net_exposure", "FLAT"),
            "hedge_factor": hedge_factor,
            "gates": {
                "edge_pass": edge_pass,
                "time_pass": time_pass,
                "atr_pass": atr_pass,
                "ob_pass": ob_pass,
                "cvd_pass": cvd_pass,
                "final_min_pass": final_min_pass,
                "all_pass": all_gates,
            },
            "components": {
                "edge": round(s_edge, 1),
                "momentum": round(s_mom, 1),
                "orderbook": round(s_ob, 1),
                "cvd": round(s_cvd, 1),
                "basis": round(s_bas, 1),
                "regime": round(s_reg, 1),
            },
        }

    # ── 6. Setup Type Classification ─────────────────────────────────────────
    def _classify_setup(self, s_edge, s_mom, s_ob, s_cvd, s_bas, s_reg,
                        regime, has_div, edge_data):
        """Tags the trade with a human-readable setup type for tracking."""
        if has_div and s_cvd >= 80:
            return "CVD_DIVERGENCE"
        if edge_data["edge_cents"] >= STRONG_EDGE_CENTS and s_bas >= 60:
            return "BASIS_CONVERGENCE"
        if regime["regime"] == "SQUEEZE" and regime["strategy"] == "BREAKOUT_IMMINENT":
            return "SQUEEZE_BREAKOUT"
        if regime["regime"] == "SQUEEZE" and regime["strategy"] == "MEAN_REVERSION":
            return "MEAN_REVERSION"
        if s_mom >= 70 and regime["strategy"] == "MOMENTUM":
            return "MOMENTUM_TREND"
        if s_ob >= 70:
            return "ORDERBOOK_IMBALANCE"
        if s_edge >= 60:
            return "EDGE_MISPRICING"

        dominant = max(
            {"EDGE": s_edge, "MOM": s_mom, "OB": s_ob,
             "CVD": s_cvd, "BASIS": s_bas},
            key=lambda k: {"EDGE": s_edge, "MOM": s_mom, "OB": s_ob,
                           "CVD": s_cvd, "BASIS": s_bas}[k],
        )
        return f"COMPOSITE_{dominant}"

    # ── 7. Smart Position Sizing ─────────────────────────────────────────────
    def calculate_smart_size(self, edge_cents: float, atr: float,
                             time_left: int, regime: dict,
                             composite_score: float,
                             hedge_factor: float = 1.0) -> float:
        """
        Conservative sizing ($1-5).  Factors in edge magnitude, volatility,
        time remaining, regime quality, and composite conviction.
        """
        base = 1.0

        # Edge multiplier: 8¢ = 1×, 15¢ = 2×, 25¢+ = 3×
        if edge_cents >= STRONG_EDGE_CENTS:
            edge_mult = min(3.0, 1.0 + (edge_cents - MIN_EDGE_CENTS) / 10.0)
        elif edge_cents >= MIN_EDGE_CENTS:
            edge_mult = 1.0 + ((edge_cents - MIN_EDGE_CENTS)
                               / max(1, STRONG_EDGE_CENTS - MIN_EDGE_CENTS))
        else:
            edge_mult = 0.5

        # Composite conviction bonus
        score_mult = 1.0 + max(0, (composite_score - MIN_COMPOSITE_SCORE) / 50.0) * 0.5

        # Regime discount
        regime_mult = {
            "CHOPPY": 0.6, "SQUEEZE": 0.8, "TRENDING": 1.0,
            "EXPANSION": 1.1, "UNKNOWN": 0.7,
        }.get(regime.get("regime", "UNKNOWN"), 0.8)

        # Time window: sweet spot is 2-12 min remaining
        if 120 < time_left < 720:
            time_mult = 1.0
        elif time_left <= 120:
            time_mult = 0.8
        else:
            time_mult = 0.9

        # Portfolio hedge: reduce if too directionally exposed
        final = base * edge_mult * score_mult * regime_mult * time_mult * hedge_factor
        return round(max(1.0, min(float(TRADE_SIZE_DOLLARS), final)), 2)
