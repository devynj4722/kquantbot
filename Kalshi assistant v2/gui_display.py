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
        self._pending_logs = []
        self._last_prime = False
        self._on_top = True
        self.is_running = True

        dpg.create_context()
        self._setup_theme()
        self._load_fonts()
        self._create_windows()
        dpg.create_viewport(title='Kalshi Quant Assistant', width=450, height=950)
        dpg.setup_dearpygui()
        dpg.show_viewport()

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
        with dpg.window(label="Kalshi Bot", tag="PrimaryWindow"):
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

            dpg.add_spacer(height=10)

            # Signal Metrics Section
            with dpg.child_window(height=230, border=True):
                with dpg.group(horizontal=True):
                    dpg.add_text("Signal Metrics", color=(255, 255, 255))
                    dpg.add_spacer(width=310)
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
                        dpg.add_text("Strike:", color=(180, 180, 180))
                    
                    # Column 2 (Values)
                    with dpg.group(width=100):
                        dpg.add_text("---", tag="atr_val")
                        dpg.add_text("---", tag="rsi_val")
                        dpg.add_text("---", tag="ev_val")
                        dpg.add_text("---", tag="dir_val")
                        dpg.add_text("---", tag="strike_val")
                        
                    # Column 3
                    with dpg.group(width=110):
                        dpg.add_text("VC Z-Score:", color=(180, 180, 180))
                        dpg.add_text("MACD Hist:", color=(180, 180, 180))
                        dpg.add_text("YES Prob:", color=(180, 180, 180))
                        dpg.add_text("Prob Trend:", color=(180, 180, 180))
                        dpg.add_text("ATR Dist:", color=(180, 180, 180))
                    
                    # Column 4 (Values)
                    with dpg.group(width=100):
                        dpg.add_text("---", tag="zscore_val")
                        dpg.add_text("---", tag="macd_val")
                        dpg.add_text("---", tag="prob_val")
                        dpg.add_text("---", tag="trend_val")
                        dpg.add_text("---", tag="atr_dist_val")

            dpg.add_spacer(height=10)

            # Orderbook Walls Section
            with dpg.child_window(height=180, border=True):
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
                with dpg.child_window(height=120, border=True, tag="decision_child"):
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
                ("ATR Dist", "Distance from strike in ATR units. >0 is above.")
            ]
            
            for title, desc in help_content:
                dpg.add_text(title, color=(0, 255, 170))
                dpg.add_text(desc, wrap=380)
                dpg.add_spacer(height=5)
            
            dpg.add_button(label="Close", callback=lambda: dpg.hide_item("help_window"))

    def run(self):
        while dpg.is_dearpygui_running():
            self._update_ui()
            dpg.render_dearpygui_frame()
        self.is_running = False
        dpg.destroy_context()

    def _update_ui(self):
        with self._lock:
            state = self._pending_state
            self._pending_state = None
            logs = list(self._pending_logs)
            self._pending_logs.clear()

        if state:
            current_price, signals = state
            self._render_state(current_price, signals)
        
        for msg in logs:
            current_val = dpg.get_value("log_text")
            dpg.set_value("log_text", current_val + msg + "\n")

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

        dpg.set_value("atr_val", f"${atr:,.2f}")
        dpg.set_value("rsi_val", f"{rsi:.1f}")
        dpg.set_value("ev_val", f"{ev:+.4f}")
        dpg.set_value("dir_val", direction)
        dpg.set_value("strike_val", f"${strike:,.2f}")
        
        dpg.set_value("zscore_val", f"{z_score:,.2f}")
        dpg.set_value("macd_val", f"{hist:+.4f}")
        dpg.set_value("prob_val", f"{prob:.0%}")
        dpg.set_value("trend_val", trend)
        dpg.set_value("atr_dist_val", f"{atr_dist:+.2f} ATR")

        # Alignment/Colors
        z_color = (255, 68, 68) if abs(z_score) >= Z_SCORE_THRESHOLD else (255, 255, 255)
        rsi_color = (255, 68, 68) if rsi > 70 else ((0, 204, 136) if rsi < 30 else (255, 255, 255))
        dir_color = (0, 255, 170) if direction == "UP" else ((255, 68, 68) if direction == "DOWN" else (128, 128, 128))
        
        dpg.configure_item("zscore_val", color=z_color)
        dpg.configure_item("rsi_val", color=rsi_color)
        dpg.configure_item("dir_val", color=dir_color)
        dpg.configure_item("ev_val", color=(0, 204, 136) if ev > 0 else (255, 255, 255))
        dpg.configure_item("macd_val", color=(0, 204, 136) if hist > 0 else (255, 68, 68))
        dpg.configure_item("trend_val", color=(0, 204, 136) if trend == "▲" else ((255, 68, 68) if trend == "▼" else (128, 128, 128)))
        dpg.configure_item("atr_dist_val", color=(255, 68, 68) if atr_dist < 0 else (0, 204, 136))

        # Walls - Format matching screenshot
        supports = signals.get('supports', [])[:5]
        resistances = signals.get('resistances', [])[:5]
        walls_str = ""
        for p, v in resistances:
            walls_str += f"RESIST  {p:.2f}   |   ${v:,.0f}\n"
        walls_str += "__________________________________________\n\n"
        for p, v in supports:
            walls_str += f"SUPPORT {round(1.0-p, 2):.2f}   |   ${v:,.0f}\n"
        dpg.set_value("walls_text", walls_str)

        # Signal banner
        is_prime = signals.get('is_good_setup', False)
        if is_prime:
            dpg.set_value("signal_label", "PRIME SETUP - ACT NOW")
            dpg.configure_item("signal_label", color=(0, 255, 170))
            bet = "YES" if direction == "UP" else "NO"
            explain = (f"Prime Setup Detected:\n"
                       f"* BTC momentum ({direction}) indicates edge.\n"
                       f"* Expected Value: {ev:+.3f}\n"
                       f"* Recommendation: Place {bet} order.")
            dpg.set_value("edge_req", explain)
            if not self._last_prime:
                self._alert_sound()
                self._update_last_trade()
        else:
            dpg.set_value("signal_label", "Monitoring... Wait for edge.")
            dpg.configure_item("signal_label", color=(150, 150, 150))
            dpg.set_value("edge_req", "Waiting for statistical edge. Prime Setup requires:\n * Z-Score >= 2.0 -- BTC 2s from 15m mean\n * EV > 0 -- momentum model beats market odds\n * 2-of-3 consensus vote (RSI, MACD, Z-Score)")
        
        self._last_prime = is_prime

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

    def update_state(self, current_price: float, signals: dict):
        with self._lock:
            self._pending_state = (current_price, signals)
