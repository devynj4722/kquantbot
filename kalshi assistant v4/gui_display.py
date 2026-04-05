import dearpygui.dearpygui as dpg
import threading
import time
from typing import Dict, Any, List
import platform
import subprocess
from config import KALSHI_SERIES, COINBASE_PRODUCT_ID, Z_SCORE_THRESHOLD, DRY_RUN
import trade_logger

class GUIDisplay:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending_state = None
        self._pending_price = None
        self._ticker_ts = 0.0
        self._pending_logs = []
        self._last_prime = False
        self._last_alert_time = 0
        self._current_anomalies = []
        self._on_top = True
        self.is_running = True
        self._pending_trade_alert = None
        self._last_popup_time = 0

        # DPG setup is handled in run()

    def _setup_theme(self):
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (15, 17, 21))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (26, 29, 36))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (40, 44, 52))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (20, 22, 27))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (226, 232, 240))
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 12, 12)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 8)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 8)

        dpg.bind_theme(global_theme)

    def _load_fonts(self):
        with dpg.font_registry():
            # Try to load a standard system font for the large price. 
            # If it fails, DPG will just use the default.
            try:
                # Common Windows path
                self.big_font = dpg.add_font("C:/Windows/Fonts/arial.ttf", 42)
                self.small_font = dpg.add_font("C:/Windows/Fonts/arial.ttf", 18)
            except:
                try:
                    # Common Mac path
                    self.big_font = dpg.add_font("/System/Library/Fonts/Helvetica.ttc", 42)
                    self.small_font = dpg.add_font("/System/Library/Fonts/Helvetica.ttc", 18)
                except:
                    self.big_font = None
                    self.small_font = None

    def _create_windows(self):
        with dpg.window(label="Kalshi BTC Pro-Quant v2.0", tag="PrimaryWindow",
                        no_close=True, no_collapse=True, no_scrollbar=True, no_move=True, no_resize=True):
            # Header Section
            with dpg.child_window(height=160, border=False, no_scrollbar=True):
                with dpg.group():
                    dpg.add_spacer(height=10)
                    with dpg.group(horizontal=True):
                        dpg.add_spacer(width=90)
                        dpg.add_text(f"Quant | {COINBASE_PRODUCT_ID} | {KALSHI_SERIES} (15m)", color=(200, 200, 200))
                    
                    with dpg.group(horizontal=True):
                        dpg.add_spacer(width=85)
                        price_text = dpg.add_text("$0.00", tag="price_label", color=(0, 255, 170))
                        if self.big_font:
                            dpg.bind_item_font(price_text, self.big_font)
                    
                    with dpg.group(horizontal=True):
                        dpg.add_spacer(width=115)
                        dpg.add_button(label="PIN Always on Top: ON", tag="on_top_btn", callback=self._toggle_on_top,
                                     width=200, height=26)
                    
                    with dpg.group(horizontal=True):
                        dpg.add_spacer(width=140)
                        dpg.add_text("Time Market closes in 00:00", tag="countdown_label", color=(150, 150, 150))

                    with dpg.group(horizontal=True):
                        dpg.add_spacer(width=165)
                        dpg.add_text("Live", color=(0, 200, 0))
                        dpg.add_text(" | Last: --ms", tag="latency_label", color=(100, 100, 100))

            dpg.add_spacer(height=10)

            # Signal Metrics Section
            with dpg.child_window(height=280, border=True, no_scrollbar=True):
                with dpg.group(horizontal=True):
                    dpg.add_text("Signal Metrics", color=(255, 255, 255))
                    dpg.add_spacer(width=220)
                    dpg.add_button(label="?", width=24, height=24, callback=self._show_help, tag="help_btn")
                
                dpg.add_spacer(height=5)
                
                # Column Layout for Metrics
                with dpg.group(horizontal=True):
                    # Column 1
                    with dpg.group(width=110):
                        dpg.add_text("15m ATR:", color=(180, 180, 180))
                        dpg.add_text("RSI:", color=(180, 180, 180))
                        dpg.add_text("EV:", color=(180, 180, 180))
                        dpg.add_text("Direction:", color=(180, 180, 180))
                        dpg.add_text("Composite:", color=(0, 255, 255))
                        dpg.add_text("Setup:", color=(0, 255, 255))
                        dpg.add_text("Gates (E/T/A/O/C):", color=(150, 150, 150))

                    # Column 2 (Values)
                    with dpg.group(width=100):
                        dpg.add_text("---", tag="atr_val")
                        dpg.add_text("---", tag="rsi_val")
                        dpg.add_text("---", tag="ev_val")
                        dpg.add_text("---", tag="dir_val")
                        dpg.add_text("---", tag="kci_val")
                        dpg.add_text("---", tag="tier_val")
                        dpg.add_text("---", tag="kswitches_val")

                    # Column 3
                    with dpg.group(width=110):
                        dpg.add_text("VC Z-Score:", color=(180, 180, 180))
                        dpg.add_text("MACD Hist:", color=(180, 180, 180))
                        dpg.add_text("Edge:", color=(0, 255, 255))
                        dpg.add_text("Strike:", color=(180, 180, 180))
                        dpg.add_text("ATR Dist:", color=(255, 170, 0))
                        dpg.add_text("Regime:", color=(180, 180, 180))
                        dpg.add_text("OI (BTC):", color=(180, 180, 180))
                        dpg.add_text("OB Imbalance:", color=(150, 150, 150))

                    # Column 4 (Values)
                    with dpg.group(width=100):
                        dpg.add_text("---", tag="zscore_val")
                        dpg.add_text("---", tag="macd_val")
                        dpg.add_text("---", tag="edge_val")
                        dpg.add_text("---", tag="strike_val")
                        dpg.add_text("---", tag="atr_dist_val")
                        dpg.add_text("---", tag="regime_val")
                        dpg.add_text("---", tag="oi_val")
                        dpg.add_text("---", tag="imbalance_val")

            dpg.add_spacer(height=10)

            # Market Insights Section (Dynamic Analysis)
            with dpg.child_window(height=190, border=True, tag="insight_window", no_scrollbar=True):
                with dpg.group(horizontal=True):
                    dpg.add_text("Market Insights & Analysis", color=(0, 255, 255))
                    dpg.add_spacer(width=160)
                    dpg.add_text("Status: Normal", tag="insight_status", color=(100, 100, 100))
                
                dpg.add_spacer(height=5)
                dpg.add_text("Monitoring institutional flow for anomalies...", tag="insight_text", wrap=400, color=(150, 150, 150))

            dpg.add_spacer(height=10)

            # Orderbook Walls Section
            with dpg.child_window(height=220, border=True, no_scrollbar=True):
                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=135)
                    dpg.add_text("Kalshi Liquidity Walls", color=(200, 200, 200))
                dpg.add_spacer(height=5)
                dpg.add_text("", tag="walls_text", wrap=0)

            dpg.add_spacer(height=10)

            # Signal Banner / Decision Panel
            with dpg.child_window(height=210, border=True, no_scrollbar=True):
                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=105)
                    dpg.add_text("Monitoring... Wait for edge.", tag="signal_label", color=(150, 150, 150))
                
                dpg.add_spacer(height=5)
                with dpg.child_window(height=125, border=True, tag="decision_child", no_scrollbar=True):
                    dpg.add_text("Waiting for statistical edge. Prime Setup requires:", tag="edge_req", color=(180, 180, 180), wrap=400)
                    dpg.add_text(" * Z-Score >= 2.0 -- BTC 2s from 15m mean", color=(150, 150, 150), wrap=400)
                    dpg.add_text(" * EV > 0 -- momentum model beats market odds", color=(150, 150, 150), wrap=400)
                    dpg.add_text(" * 2-of-3 consensus vote (RSI, MACD, Z-Score)", color=(150, 150, 150), wrap=400)

                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=140)
                    dpg.add_text("Last signal: none", tag="last_trade_label", color=(85, 85, 85))
                
                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=155)
                    dry_tag = "[DRY RUN MODE]" if DRY_RUN else "[LIVE TRADING]"
                    mode_color = (255, 170, 0) if DRY_RUN else (255, 68, 68)
                    dpg.add_text(dry_tag, color=mode_color)

            dpg.add_spacer(height=10)

            # Logs (Hidden/Minimalist scrollbox)
            dpg.add_input_text(multiline=True, readonly=True, tag="log_text", height=120, width=-1)

        dpg.set_primary_window("PrimaryWindow", True)

    def _toggle_on_top(self):
        self._on_top = not self._on_top
        dpg.set_viewport_always_top(self._on_top)
        label = "PIN Always on Top: ON" if self._on_top else "PIN Always on Top: OFF"
        dpg.configure_item("on_top_btn", label=label)

    def _show_insight_popup(self, anomaly: dict, title: str = "INSTITUTIONAL ALERT"):
        # Don't replace a popup that's less than 3 seconds old
        if dpg.does_item_exist("alert_popup"):
            if time.time() - self._last_popup_time < 3.0:
                return  # Let the existing popup stay visible
            dpg.delete_item("alert_popup")

        try:
            with dpg.window(label=title, modal=True, show=True,
                            tag="alert_popup", width=350, height=200, pos=[50, 250], no_resize=True):
                color = (0, 255, 170) if "PRIME" in title else (255, 68, 68)
                dpg.add_text(anomaly['alert'], color=color)
                dpg.add_separator()
                dpg.add_spacer(height=5)
                dpg.add_text(anomaly['explanation'], wrap=330)
                dpg.add_spacer(height=15)
                dpg.add_button(label="ACKNOWLEDGE", width=120, callback=lambda: dpg.delete_item("alert_popup"))
            self._last_popup_time = time.time()
        except Exception:
            pass  # DPG tag collision — don't crash the render loop

    def _show_trade_popup(self, alert: dict):
        """Large, high-visibility popup when a position is taken."""
        tag = "trade_exec_popup"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        # Also dismiss any edge-detection popup so they don't stack
        if dpg.does_item_exist("alert_popup"):
            dpg.delete_item("alert_popup")

        mode = "DRY RUN" if alert["dry_run"] else "LIVE ORDER"
        side = alert["side"]
        side_color = (0, 255, 170) if side == "YES" else (255, 85, 85)
        header_color = (255, 200, 50)  # Gold for trade alerts

        try:
            with dpg.window(label=f"TRADE EXECUTED — {mode}", modal=True, show=True,
                            tag=tag, width=420, height=280, pos=[30, 180],
                            no_resize=True, no_collapse=True):
                # Big header
                dpg.add_text(f"POSITION TAKEN", color=header_color)
                dpg.add_text(f"{mode}", color=(180, 180, 180))
                dpg.add_separator()
                dpg.add_spacer(height=5)

                # Trade details
                dpg.add_text(f"Side:      {side}", color=side_color)
                dpg.add_text(f"Ticker:    {alert['ticker']}")
                dpg.add_text(
                    f"Size:      ${alert['size_dollars']:.2f}  "
                    f"({alert['contracts']}x @ {alert['limit_price']}¢)")
                dpg.add_text(f"Score:     {alert['composite_score']:.1f}")
                dpg.add_text(f"Setup:     {alert['setup_type']}", color=(0, 200, 255))
                dpg.add_spacer(height=10)
                dpg.add_separator()
                dpg.add_spacer(height=8)
                dpg.add_button(label="OK", width=380,
                               callback=lambda: dpg.delete_item(tag))
            self._last_popup_time = time.time()
        except Exception:
            pass  # DPG tag collision — don't crash the render loop

    def _show_help(self):
        if dpg.does_item_exist("help_window"):
            dpg.show_item("help_window")
            return

        with dpg.window(label="Signal Metrics - Help", tag="help_window", width=400, height=500, pos=(25, 100)):
            dpg.add_text("What Each Metric Means", color=(0, 255, 170))
            dpg.add_separator()
            
            help_content = [
                ("15m ATR", "Average True Range over 15 1-min candles. Measures volatility."),
                ("Z-Score", "Price deviation from 15m mean. Threshold: ±2.0."),
                ("RSI", "Relative Strength Index. >70 Overbought, <30 Oversold."),
                ("MACD Hist", "Momentum shift signal. Positive is bullish."),
                ("EV", "Expected Value vs Market probability. Must be > 0."),
                ("YES Prob", "Market implied probability (1 - best NO ask)."),
                ("Direction", "2-of-3 consensus vote (RSI, MACD, Z-Score)."),
                ("ATR Dist", "Distance from strike in ATR units. >0 is above."),
                ("CVD", "Cumulative Volume Delta. Tracks market order pressure (Buys vs Sells). Divergence can spot 'fake pumps'."),
                ("Open Int", "Open Interest. Total active futures contracts. High OI = high leverage = 'coiled spring' for wicks.")
            ]
            
            for title, desc in help_content:
                dpg.add_text(title, color=(0, 255, 170))
                dpg.add_text(desc, wrap=380)
                dpg.add_spacer(height=5)
            
            dpg.add_button(label="Close", callback=lambda: dpg.hide_item("help_window"))

    def run(self):
        dpg.create_context()
        self._setup_theme()
        self._load_fonts()
        self._create_windows()
        dpg.create_viewport(title='Kalshi BTC Pro-Quant', width=540, height=1050, resizable=True)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        
        while dpg.is_dearpygui_running():
            self._update_ui()
            dpg.render_dearpygui_frame()
            
        self.is_running = False
        dpg.destroy_context()

    def _update_ui(self):
        with self._lock:
            state = self._pending_state
            self._pending_state = None
            price = self._pending_price
            self._pending_price = None
            logs = list(self._pending_logs)
            self._pending_logs.clear()
            trade_alert = self._pending_trade_alert
            self._pending_trade_alert = None

        # ── Trade Execution Popup ────────────────────────────────────────
        if trade_alert:
            self._show_trade_popup(trade_alert)

        # Update Live Latency Indicator on every frame
        if self._ticker_ts > 0:
            diff = time.time() - self._ticker_ts
            if diff < 1.0:
                dpg.set_value("latency_label", f" | Last: {int(diff*1000)}ms")
                dpg.configure_item("latency_label", color=(100, 100, 100))
            else:
                dpg.set_value("latency_label", f" | STALE: {diff:.1f}s")
                dpg.configure_item("latency_label", color=(255, 68, 68))

        if price:
            dpg.set_value("price_label", f"${price:,.2f}")
        
        if state:
            current_price, signals = state
            self._render_state(current_price, signals)
        
        for msg in logs:
            current_val = dpg.get_value("log_text")
            # Truncate to last 100 lines for performance
            lines = current_val.split("\n")[-100:]
            dpg.set_value("log_text", "\n".join(lines) + msg + "\n")

    def _render_state(self, current_price, signals):
        dpg.set_value("price_label", f"${current_price:,.2f}")
        
        time_left = signals.get('time_left', 0)
        mins, secs = divmod(time_left, 60)
        cd_text = f"T-Minus Market closes in {mins:02d}:{secs:02d}"
        
        # Color coding: Green > 5m, Orange 1-5m, Red < 1m
        if time_left > 300:
            cd_color = (0, 204, 136) # Green
        elif time_left > 60:
            cd_color = (255, 170, 0) # Orange
        else:
            cd_color = (255, 68, 68) # Red
            
        dpg.set_value("countdown_label", cd_text)
        dpg.configure_item("countdown_label", color=cd_color)
        atr = signals.get('atr', 0.0)
        z_score = signals.get('z_score', 0.0)
        rsi = signals.get('rsi', 0.0)
        ev = signals.get('ev', 0.0)
        hist = signals.get('macd', {}).get('histogram', 0.0)
        direction = signals.get('signal_direction', 'NEUTRAL')
        trend = signals.get('prob_trend', '─')
        prob = signals.get('p_win_estimate', 0.5)
        strike = signals.get('strike_price', 0.0)
        atr_dist = signals.get('atr_distance', 0.0)
        cvd = signals.get('cvd', 0.0)
        oi = signals.get('binance_oi', 0.0)
        oi_source = signals.get('oi_source', '???')

        dpg.set_value("atr_val", f"${atr:,.2f}")
        dpg.set_value("rsi_val", f"{rsi:.1f}")
        dpg.set_value("ev_val", f"{ev:+.4f}")
        dpg.set_value("dir_val", direction)

        # Strike
        if strike > 0:
            dpg.set_value("strike_val", f"${strike:,.2f}")
        else:
            dpg.set_value("strike_val", "---")

        dpg.set_value("zscore_val", f"{z_score:,.2f}")
        dpg.set_value("macd_val", f"{hist:+.4f}")

        # Edge (cents) — new primary metric
        edge_cents = signals.get('edge_cents', 0.0)
        edge_dir = signals.get('edge_direction', 'FAIR')
        dpg.set_value("edge_val", f"{edge_cents:.1f}¢ ({edge_dir[:3]})")
        edge_color = (0, 255, 170) if edge_cents >= 15 else ((255, 170, 0) if edge_cents >= 8 else (150, 150, 150))
        dpg.configure_item("edge_val", color=edge_color)

        # ATR Distance (from strike in ATR units) — gate: must be < 2.0 (or 1.0 in last 5min)
        from config import ATR_DIST_KILL_SWITCH
        time_left = signals.get('time_left', 900)
        atr_limit = ATR_DIST_KILL_SWITCH if time_left > 300 else 1.0
        atr_dist_abs = abs(atr_dist)
        atr_pass = atr_dist_abs < atr_limit if strike > 0 else True
        above_below = "above" if atr_dist > 0 else "below"
        dpg.set_value("atr_dist_val", f"{atr_dist_abs:.2f} ({above_below}) / {atr_limit:.1f}")
        if not atr_pass:
            dpg.configure_item("atr_dist_val", color=(255, 68, 68))
        elif atr_dist_abs > atr_limit * 0.7:
            dpg.configure_item("atr_dist_val", color=(255, 170, 0))
        else:
            dpg.configure_item("atr_dist_val", color=(0, 255, 170))

        # Regime
        regime_data = signals.get('regime', {})
        regime_str = regime_data.get('regime', '---')
        regime_strat = regime_data.get('strategy', '')
        phase = signals.get('time_phase', '')
        dpg.set_value("regime_val", f"{regime_str} ({phase})")
        regime_color = {
            "TRENDING": (0, 204, 136), "EXPANSION": (0, 255, 255),
            "SQUEEZE": (255, 170, 0), "CHOPPY": (255, 68, 68)
        }.get(regime_str, (150, 150, 150))
        dpg.configure_item("regime_val", color=regime_color)

        # OI
        oi_pct = signals.get('anomalies', {}).get('metrics', {}).get('oi_pct_15m', 0.0)
        dpg.set_value("oi_val", f"{oi:,.0f} ({oi_pct:+.1%}) ({oi_source})")

        # Orderbook Imbalance
        imb = signals.get('imbalance', {})
        imb_ratio = imb.get('imbalance_ratio', 1.0)
        imb_dir = imb.get('imbalance_direction', 'NEUTRAL')
        dpg.set_value("imbalance_val", f"{imb_ratio:.1f}:1 ({imb_dir[:3]})")
        imb_color = (0, 255, 170) if imb_dir == "YES_PRESSURE" else ((255, 68, 68) if imb_dir == "NO_PRESSURE" else (150, 150, 150))
        dpg.configure_item("imbalance_val", color=imb_color)

        # Composite Score (replaces KCI)
        composite = signals.get('composite_score', 0.0)
        dpg.set_value("kci_val", f"{composite:.1f}")

        # Setup type (replaces tier)
        setup_type = signals.get('setup_type', 'NONE')
        dpg.set_value("tier_val", setup_type)

        # Composite colors
        comp_color = (150, 150, 150)
        if composite >= 70: comp_color = (0, 255, 170)
        elif composite >= 55: comp_color = (255, 170, 0)
        elif composite > 0: comp_color = (255, 68, 68)
        dpg.configure_item("kci_val", color=comp_color)
        dpg.configure_item("tier_val", color=comp_color)

        # Gates (Edge / Time / ATR / Orderbook / CVD-fade)
        gates = signals.get('composite_gates', {})
        ge = gates.get('edge_pass', False)
        gt = gates.get('time_pass', False)
        ga = gates.get('atr_pass', False)
        go = gates.get('ob_pass', False)
        gc = gates.get('cvd_pass', True)
        g_str = f"{'OK' if ge else 'NO'} / {'OK' if gt else 'NO'} / {'OK' if ga else 'NO'} / {'OK' if go else 'NO'} / {'OK' if gc else 'NO'}"
        all_pass = gates.get('all_pass', False)
        dpg.set_value("kswitches_val", g_str)
        dpg.configure_item("kswitches_val", color=(0, 255, 0) if all_pass else (255, 100, 100))

        # Broadcast state for separate KCI widget
        try:
            import json
            state = {
                "kci": composite,
                "tier": setup_type,
                "w_sum": composite,
                "direction": signals.get('signal_direction', 'NEUTRAL'),
                "k_factor": all_pass,
                "price": current_price,
                "edge_cents": edge_cents,
                "strike": signals.get("strike", 0.0),
                "countdown": dpg.get_value("countdown_label"),
                "timestamp": time.time()
            }
            with open("kci_state.json", "w") as f:
                json.dump(state, f)
        except Exception:
            pass

        z_color = (255, 68, 68) if abs(z_score) >= Z_SCORE_THRESHOLD else (255, 255, 255)
        rsi_color = (255, 68, 68) if rsi > 70 else ((0, 204, 136) if rsi < 30 else (255, 255, 255))
        dir_color = (0, 255, 170) if direction == "UP" else ((255, 68, 68) if direction == "DOWN" else (128, 128, 128))

        dpg.configure_item("zscore_val", color=z_color)
        dpg.configure_item("rsi_val", color=rsi_color)
        dpg.configure_item("dir_val", color=dir_color)
        dpg.configure_item("ev_val", color=(0, 204, 136) if ev > 0 else (255, 255, 255))
        dpg.configure_item("macd_val", color=(0, 204, 136) if hist > 0 else (255, 68, 68))
        dpg.configure_item("oi_val", color=(0, 255, 255))

        # Market Insights (Tiered CVD/Price)
        anomaly_data = signals.get('anomalies', {})
        anom_metrics = anomaly_data.get('metrics', {})
        p15 = anom_metrics.get('price_delta_15m', 0)
        c15 = anom_metrics.get('cvd_delta_15m', 0)
        p60 = anom_metrics.get('price_delta_60m', 0)
        c60 = anom_metrics.get('cvd_delta_60m', 0)
        
        # Determine filling status
        i15 = anom_metrics.get('idx_15m', 0)
        i60 = anom_metrics.get('idx_60m', 0)
        stat15 = f"{i15/60:.1f}m"
        stat60 = f"{i60/60:.1f}m"

        # ── Live Indicator Summary ────────────────────────────────────
        _comps = signals.get('composite_components', {})
        _gates = signals.get('composite_gates', {})
        _regime_str = signals.get('regime', {}).get('regime', '---')
        _phase = signals.get('time_phase', '?')
        _cvd_v = signals.get('cvd_confirm', {}).get('cvd_verdict', '?')
        _edge_d = signals.get('edge_direction', 'FAIR')
        _ob_dir = signals.get('imbalance', {}).get('imbalance_direction', '?')

        def _g(k):
            return "+" if _gates.get(k, False) else "-"

        insight_lines = [
            f"Edge: {edge_cents:.1f}¢ ({_edge_d}) | Score: {composite:.0f}/100 | Regime: {_regime_str} ({_phase})",
            f"Components: E:{_comps.get('edge',0):.0f} M:{_comps.get('momentum',0):.0f} "
            f"OB:{_comps.get('orderbook',0):.0f} CVD:{_comps.get('cvd',0):.0f} "
            f"Bas:{_comps.get('basis',0):.0f} Reg:{_comps.get('regime',0):.0f}",
            f"Gates: E({_g('edge_pass')}) T({_g('time_pass')}) A({_g('atr_pass')}) "
            f"OB({_g('ob_pass')}) CVD({_g('cvd_pass')}) F({_g('final_min_pass')}) "
            f"| CVD: {_cvd_v} | OB: {_ob_dir}",
            f"15m: Price ${p15:+.1f} | CVD {c15:+.1f} BTC   "
            f"60m: Price ${p60:+.1f} | CVD {c60:+.1f} BTC",
        ]
        
        active_alerts = anomaly_data.get('alerts', [])
        if active_alerts:
            insight_lines.append("")
            insight_lines.append("--- ACTIVE ANOMALIES ---")
            for a in active_alerts:
                insight_lines.append(f"!! {a['alert']} !!")
                insight_lines.append(f"   {a['explanation']}")
            dpg.set_value("insight_status", "!! ANOMALY DETECTED !!")
            dpg.configure_item("insight_status", color=(255, 68, 68))
            
            # Trigger Popup if it's been more than 60s
            if time.time() - self._last_alert_time > 60:
                self._show_insight_popup(active_alerts[0])
                if "Leverage" in active_alerts[0]['alert']:
                    self._flush_sound()
                else:
                    self._alert_sound()
                self._last_alert_time = time.time()
        else:
            dpg.set_value("insight_status", "Status: Normal")
            dpg.configure_item("insight_status", color=(100, 100, 100))
        
        dpg.set_value("insight_text", "\n".join(insight_lines))
        dpg.configure_item("insight_text", color=(200, 200, 200))

        # Walls - Format matching YES/NO payoff
        supports = signals.get('supports', [])[:5]
        resistances = signals.get('resistances', [])[:5]
        
        if not supports and not resistances:
            walls_str = "Monitoring orderbook... No major walls detected."
        else:
            walls_str = ""
            for p, v in resistances:
                # p is the price of the 'NO' contract
                yes_p = round(1.0 - p, 2)
                walls_str += f"RESIST  {yes_p:.2f} (YES) | {v:,.0f} contracts\n"
            
            walls_str += "__________________________________________\n\n"
            
            for p, v in supports:
                # p is the price of the 'NO' contract
                yes_p = round(1.0 - p, 2)
                walls_str += f"SUPPORT {yes_p:.2f} (YES) | {v:,.0f} contracts\n"
        
        dpg.set_value("walls_text", walls_str)

        # Signal banner — now driven by composite score + edge engine
        should_trade = signals.get('should_trade', False)
        cvd_verdict = signals.get('cvd_confirm', {}).get('cvd_verdict', 'N/A')
        smart_size = signals.get('smart_size', 1.0)
        hedge_info = signals.get('hedge', {})

        if should_trade:
            dpg.set_value("signal_label", f"MISPRICED CONTRACT ({setup_type} | {composite:.0f})")
            dpg.configure_item("signal_label", color=(0, 255, 170))
            bet = "YES" if direction == "UP" else "NO"
            comps = signals.get('composite_components', {})
            explain = (
                f"Edge: {edge_cents:.1f}¢ | Score: {composite:.1f} | Size: ${smart_size:.2f}\n"
                f"* Setup: {setup_type} | CVD: {cvd_verdict} | Phase: {signals.get('time_phase', '?')}\n"
                f"* Components: E:{comps.get('edge',0):.0f} M:{comps.get('momentum',0):.0f} "
                f"OB:{comps.get('orderbook',0):.0f} CVD:{comps.get('cvd',0):.0f} "
                f"Bas:{comps.get('basis',0):.0f} Reg:{comps.get('regime',0):.0f}\n"
                f"* Exposure: {hedge_info.get('net_exposure', 'FLAT')} | Action: {bet}")
            dpg.set_value("edge_req", explain)
            if not self._last_prime:
                self._show_insight_popup(
                    {"alert": f"MISPRICED: {setup_type}", "explanation": explain},
                    title="EDGE DETECTED")
                self._alert_sound()
                self._last_alert_time = time.time()
        else:
            dpg.set_value("signal_label", f"Scanning... (Score: {composite:.0f} | Edge: {edge_cents:.1f}¢)")
            dpg.configure_item("signal_label", color=(150, 150, 150))
            # Show why we're not trading
            blocked = []
            if not gates.get('edge_pass', False): blocked.append(f"Edge < 8¢ ({edge_cents:.1f}¢)")
            if not gates.get('time_pass', False): blocked.append("Time filter (57-05)")
            if not gates.get('atr_pass', False):
                _ad = abs(signals.get('atr_distance', 0))
                _tl = signals.get('time_left', 900)
                _al = 2.0 if _tl > 300 else 1.0
                blocked.append(f"ATR dist {_ad:.2f} > {_al:.1f} limit")
            if not gates.get('ob_pass', False): blocked.append("Orderbook counter-aligned")
            if not gates.get('cvd_pass', True): blocked.append(f"CVD FADE ({cvd_verdict})")
            if composite < 55: blocked.append(f"Score < 55 ({composite:.1f})")
            block_str = " | ".join(blocked) if blocked else "Waiting for setup alignment"
            dpg.set_value("edge_req", f"Blocked: {block_str}\n\nRequires:\n * Edge >= 8¢ mispricing\n * Composite Score >= 55 (6 weighted signals)\n * All gates pass (Edge/Time/ATR/OB/CVD)")

        self._last_prime = should_trade

    def _alert_sound(self):
        def _play():
            sys_platform = platform.system()
            if sys_platform == "Windows":
                import winsound
                winsound.Beep(880, 150)
                winsound.Beep(1100, 150)
                winsound.Beep(1320, 200)
            elif sys_platform == "Darwin":  # Mac
                subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"])
        threading.Thread(target=_play, daemon=True).start()
        
    def _flush_sound(self):
        """Cross-platform, non-blocking institutional alert."""
        def play():
            try:
                sys_platform = platform.system()
                if sys_platform == "Windows":
                    import winsound
                    winsound.Beep(1500, 100)
                    winsound.Beep(1800, 150)
                elif sys_platform == "Darwin": # Mac
                    subprocess.run(["afplay", "/System/Library/Sounds/Tink.aiff"])
                    subprocess.run(["afplay", "/System/Library/Sounds/Tink.aiff"])
            except:
                pass

        threading.Thread(target=play, daemon=True).start()

    def _trade_executed_sound(self):
        """Loud, unmistakable 3-tone alert when a position is actually taken."""
        def play():
            try:
                sys_platform = platform.system()
                if sys_platform == "Windows":
                    import winsound
                    # Ascending 5-tone fanfare — impossible to miss
                    for freq, dur in [(660, 120), (880, 120), (1100, 120), (1320, 150), (1760, 300)]:
                        winsound.Beep(freq, dur)
                elif sys_platform == "Darwin":
                    # Triple system sound for urgency
                    subprocess.run(["afplay", "/System/Library/Sounds/Hero.aiff"])
                    time.sleep(0.15)
                    subprocess.run(["afplay", "/System/Library/Sounds/Hero.aiff"])
                else:
                    # Linux fallback
                    subprocess.run(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                                   capture_output=True)
            except:
                pass
        threading.Thread(target=play, daemon=True).start()

    def notify_trade_executed(self, side: str, ticker: str, size_dollars: float,
                              composite_score: float, setup_type: str,
                              contracts: int = 0, limit_price: int = 0,
                              dry_run: bool = True):
        """
        Called by data_ingestion when a position is taken (DRY_RUN or live).
        Shows a prominent popup + plays the trade execution sound.
        """
        mode = "DRY RUN" if dry_run else "LIVE ORDER"
        trade_msg = (
            f"{'=' * 40}\n"
            f"  POSITION TAKEN ({mode})\n"
            f"{'=' * 40}\n"
            f"  Side:     {side.upper()}\n"
            f"  Ticker:   {ticker}\n"
            f"  Size:     ${size_dollars:.2f} ({contracts}x @ {limit_price}¢)\n"
            f"  Score:    {composite_score:.1f}\n"
            f"  Setup:    {setup_type}\n"
            f"{'=' * 40}"
        )
        # Log prominently to terminal
        with self._lock:
            self._pending_logs.append(f"\n{'*' * 50}")
            self._pending_logs.append(f"TRADE EXECUTED: {side.upper()} ${size_dollars:.2f} on {ticker}")
            self._pending_logs.append(f"  Score: {composite_score:.1f} | Setup: {setup_type} | {mode}")
            self._pending_logs.append(f"{'*' * 50}\n")
            # Queue the GUI popup + sound to run on the DPG thread
            self._pending_trade_alert = {
                "side": side.upper(),
                "ticker": ticker,
                "size_dollars": size_dollars,
                "composite_score": composite_score,
                "setup_type": setup_type,
                "contracts": contracts,
                "limit_price": limit_price,
                "dry_run": dry_run,
                "msg": trade_msg,
            }
        # Sound fires immediately from any thread
        self._trade_executed_sound()

    def _update_last_trade(self):
        sig = trade_logger.get_last_signal()
        if sig:
            dpg.set_value("last_trade_label", f"Last: {sig['direction']} | EV {sig['ev']} | {sig['timestamp'][:19]}")

    def log_error(self, message: str):
        with self._lock:
            self._pending_logs.append(f"ERROR: {message}")

    def log_info(self, message: str):
        with self._lock:
            self._pending_logs.append(f"INFO: {message}")

    def update_state(self, current_price: float, signals: dict, ts: float = None):
        with self._lock:
            self._pending_state = (current_price, signals)
            self._pending_price = current_price
            if ts: self._ticker_ts = ts

    def update_price_only(self, price: float, ts: float = None):
        with self._lock:
            self._pending_price = price
            if ts: self._ticker_ts = ts
