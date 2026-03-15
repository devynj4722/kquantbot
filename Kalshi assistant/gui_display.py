import customtkinter as ctk
from typing import Dict, Any, List
import threading
import winsound
from config import KALSHI_SERIES, COINBASE_PRODUCT_ID, Z_SCORE_THRESHOLD, DRY_RUN
import trade_logger

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# System tray icon (optional — imported lazily)
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False


def _make_tray_icon_image():
    img = Image.new("RGB", (64, 64), color=(15, 15, 30))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, 56, 56], fill=(0, 200, 120))
    return img


class GUIDisplay(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Kalshi Quant Assistant")
        self.geometry("430x820")
        self.attributes("-topmost", True)
        self._tray_icon = None
        self._last_prime = False

        # Initialize thread-safe state FIRST — background threads may call log_error
        # before __init__ finishes constructing widgets
        import threading as _threading
        self._lock = _threading.Lock()
        self._pending_state = None
        self._pending_logs = []

        # ── Header ──────────────────────────────────────────────────────────
        self.header_frame = ctk.CTkFrame(self)
        self.header_frame.pack(pady=8, padx=10, fill="x")

        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text=f"Quant | {COINBASE_PRODUCT_ID} | {KALSHI_SERIES} (15m)",
            font=("Arial", 13, "bold"))
        self.title_label.pack(pady=(6, 0))

        self.price_label = ctk.CTkLabel(
            self.header_frame, text="$0.00",
            font=("Arial", 26, "bold"), text_color="#00FFAA")
        self.price_label.pack(pady=2)

        # Always-on-top toggle
        self._always_on_top = True
        self._pin_btn = ctk.CTkButton(
            self.header_frame, text="📌 Always on Top: ON",
            width=170, height=22, font=("Arial", 10),
            fg_color="#1e3a2a", hover_color="#2a5a3a",
            command=self._toggle_on_top)
        self._pin_btn.pack(pady=(0, 2))

        self.countdown_label = ctk.CTkLabel(
            self.header_frame, text="⏱  Market closes in --:--",
            font=("Arial", 11), text_color="#888888")
        self.countdown_label.pack(pady=(0, 6))

        # ── Metrics Panel ────────────────────────────────────────────────────
        self.metrics_frame = ctk.CTkFrame(self)
        self.metrics_frame.pack(pady=6, padx=10, fill="x")

        title_row = ctk.CTkFrame(self.metrics_frame, fg_color="transparent")
        title_row.pack(pady=(6, 0), padx=10, fill="x")
        ctk.CTkLabel(title_row, text="Signal Metrics",
                     font=("Arial", 12, "bold")).pack(side="left", padx=(4, 0))
        ctk.CTkButton(title_row, text="?", width=22, height=22,
                      font=("Arial", 11, "bold"),
                      fg_color="#333355", hover_color="#4444AA",
                      corner_radius=11,
                      command=self._show_help).pack(side="right", padx=(0, 4))

        grid = ctk.CTkFrame(self.metrics_frame, fg_color="transparent")
        grid.pack(padx=10, pady=(0, 6), fill="x")
        grid.columnconfigure((0, 1), weight=1)

        def _metric(parent, label, row, col):
            lbl = ctk.CTkLabel(parent, text=label, font=("Arial", 11), anchor="w")
            lbl.grid(row=row, column=col * 2, sticky="w", padx=(0, 4), pady=1)
            val = ctk.CTkLabel(parent, text="---", font=("Arial", 11, "bold"), anchor="e")
            val.grid(row=row, column=col * 2 + 1, sticky="e", padx=(0, 12), pady=1)
            return val

        grid.columnconfigure((0, 1, 2, 3), weight=1)
        self.atr_val      = _metric(grid, "15m ATR:",    0, 0)
        self.zscore_val   = _metric(grid, "VC Z-Score:", 0, 1)
        self.rsi_val      = _metric(grid, "RSI:",        1, 0)
        self.macd_val     = _metric(grid, "MACD Hist:",  1, 1)
        self.ev_val       = _metric(grid, "EV:",         2, 0)
        self.prob_val     = _metric(grid, "YES Prob:",   2, 1)
        self.dir_val      = _metric(grid, "Direction:",  3, 0)
        self.ev_trend     = _metric(grid, "Prob Trend:", 3, 1)
        self.strike_val   = _metric(grid, "Strike:",     4, 0)
        self.atr_dist_val = _metric(grid, "ATR Dist:",   4, 1)

    def _show_help(self):
        """Opens a floating explanation window for all signal metrics."""
        win = ctk.CTkToplevel(self)
        win.title("Signal Metrics — Help")
        win.geometry("420x540")
        win.attributes("-topmost", True)
        win.grab_set()  # modal

        ctk.CTkLabel(win, text="What Each Metric Means",
                     font=("Arial", 14, "bold")).pack(pady=(14, 6), padx=16)

        explanations = [
            ("15m ATR",
             "Average True Range over 15 one-minute candles.\n"
             "Measures how much BTC is moving per candle.\n"
             "High ATR = volatile market. Low ATR = quiet market.\n"
             "Use it to gauge risk — higher ATR means bigger swings."),
            ("Z-Score",
             "How many standard deviations BTC's current price is\n"
             "from its recent 15m average.\n"
             "• > +2.0 → BTC unusually HIGH → possible mean-reversion DOWN\n"
             "• < -2.0 → BTC unusually LOW  → possible mean-reversion UP\n"
             "Threshold: ±2.0 required for Prime Setup."),
            ("RSI",
             "Relative Strength Index (14-period).\n"
             "Measures speed and magnitude of recent price moves.\n"
             "• > 70 → Overbought (red) — momentum may reverse down\n"
             "• < 30 → Oversold  (green) — momentum may reverse up\n"
             "• 30–70 → Neutral range"),
            ("MACD Hist",
             "MACD Histogram (12/26/9 EMA).\n"
             "Difference between the MACD line and its signal line.\n"
             "• Positive (green) → upward momentum building\n"
             "• Negative (red)   → downward momentum building\n"
             "Crossing zero = momentum shift signal."),
            ("EV (Expected Value)",
             "Your model's edge vs the Kalshi market price.\n"
             "EV = model_probability − market_implied_probability\n"
             "• Positive → your momentum signal exceeds market odds\n"
             "• Negative → market is priced better than your signal\n"
             "Must be > 0 for Prime Setup."),
            ("YES Prob",
             "Market-implied probability that BTC closes ABOVE the\n"
             "strike at expiry, derived from the Kalshi orderbook.\n"
             "= 1 − best NO ask price"),
            ("Direction",
             "2-of-3 consensus vote between RSI, MACD, and Z-Score.\n"
             "• UP   → majority of signals say BTC goes higher → bet YES\n"
             "• DOWN → majority say BTC goes lower → bet NO\n"
             "• NEUTRAL → signals disagree → no trade"),
            ("Prob Trend",
             "Direction the Kalshi YES implied probability has moved\n"
             "over the last 5 orderbook updates.\n"
             "▲ Rising → market participants buying YES (bullish)\n"
             "▼ Falling → market participants buying NO (bearish)\n"
             "Use this to confirm or question the Direction signal."),
        ]

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        for title, desc in explanations:
            block = ctk.CTkFrame(scroll, fg_color="#1e1e2e", corner_radius=8)
            block.pack(fill="x", pady=4)
            ctk.CTkLabel(block, text=title, font=("Arial", 11, "bold"),
                         text_color="#00FFAA", anchor="w").pack(
                         padx=10, pady=(6, 0), anchor="w")
            ctk.CTkLabel(block, text=desc, font=("Arial", 10),
                         text_color="#CCCCCC", anchor="w", justify="left",
                         wraplength=370).pack(
                         padx=10, pady=(2, 8), anchor="w")

        ctk.CTkButton(win, text="Close", command=win.destroy,
                      fg_color="#333355", hover_color="#4444AA").pack(pady=(0, 12))

        # ── Orderbook Walls ──────────────────────────────────────────────────
        self.walls_frame = ctk.CTkFrame(self)
        self.walls_frame.pack(pady=6, padx=10, fill="both", expand=True)
        ctk.CTkLabel(self.walls_frame, text="Kalshi Liquidity Walls",
                     font=("Arial", 13, "bold")).pack(pady=(6, 2))
        self.walls_text = ctk.CTkTextbox(self.walls_frame, state="disabled",
                                         font=("Courier", 11))
        self.walls_text.pack(pady=(0, 6), padx=10, fill="both", expand=True)

        # ── Signal Banner ────────────────────────────────────────────────────
        self.footer_frame = ctk.CTkFrame(self)
        self.footer_frame.pack(pady=6, padx=10, fill="x")
        self.signal_label = ctk.CTkLabel(
            self.footer_frame, text="Monitoring... Wait for edge.",
            text_color="gray", font=("Arial", 14, "bold"))
        self.signal_label.pack(pady=(8, 2))
        self.signal_explain = ctk.CTkTextbox(
            self.footer_frame, state="disabled", height=100,
            font=("Arial", 11), wrap="word", fg_color="#1a1a1a")
        self.signal_explain.pack(pady=(0, 4), padx=10, fill="x")
        self._set_explanation(False)

        # ── Last Trade ───────────────────────────────────────────────────────
        self.last_trade_label = ctk.CTkLabel(
            self.footer_frame, text="Last signal: none",
            font=("Arial", 10), text_color="#555555")
        self.last_trade_label.pack(pady=(0, 2))

        dry_tag = "  [DRY RUN MODE]" if DRY_RUN else "  [LIVE TRADING]"
        self.mode_label = ctk.CTkLabel(
            self.footer_frame,
            text=dry_tag,
            font=("Arial", 10, "bold"),
            text_color="#FFAA00" if DRY_RUN else "#FF4444")
        self.mode_label.pack(pady=(0, 4))

        # ── Log box ──────────────────────────────────────────────────────────
        self.info_text = ctk.CTkTextbox(self, state="disabled", height=55,
                                        font=("Courier", 9))
        self.info_text.pack(pady=(0, 6), padx=10, fill="x")

        # ── Rate-limited state ────────────────────────────────────────────────
        self.is_running = True
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self._render_cache: dict = {}   # tracks last-rendered metric values
        self._walls_cache: str = ""    # tracks last-rendered walls string
        self.after(250, self._poll_ui)

    # ── Poll Loop (main thread, 250ms) ────────────────────────────────────────
    def _poll_ui(self):
        if not self.is_running:
            return
        with self._lock:
            state = self._pending_state
            self._pending_state = None
            logs = list(self._pending_logs)
            self._pending_logs.clear()
        if state is not None:
            self._update_state_internal(*state)
        for msg in logs:
            self._append_log(msg)
        self.after(250, self._poll_ui)

    # ── Thread-safe write (background threads) ────────────────────────────────
    def log_error(self, message: str):
        with self._lock:
            self._pending_logs.append(f"ERROR: {message}")

    def log_info(self, message: str):
        with self._lock:
            self._pending_logs.append(f"INFO: {message}")

    def update_state(self, current_price: float, signals: dict):
        with self._lock:
            self._pending_state = (current_price, signals)

    # ── Internal render (main thread only) ───────────────────────────────────
    def _append_log(self, msg: str):
        self.info_text.configure(state="normal")
        self.info_text.insert("end", msg + "\n")
        self.info_text.see("end")
        self.info_text.configure(state="disabled")

    def _set(self, key, widget, text, text_color=None):
        """Only call widget.configure() if the value or color actually changed."""
        cached = self._render_cache.get(key)
        new_val = (text, text_color)
        if cached == new_val:
            return
        self._render_cache[key] = new_val
        kw = {"text": text}
        if text_color is not None:
            kw["text_color"] = text_color
        widget.configure(**kw)

    def _update_state_internal(self, current_price: float, signals: Dict[str, Any]):
        # Price — format to 2 dp, only update on change
        price_str = f"${current_price:,.2f}"
        self._set("price", self.price_label, price_str)

        # Countdown — update every second but cheaply
        time_left = signals.get('time_left', 0)
        mins, secs = divmod(time_left, 60)
        cd_text  = f"⏱  Market closes in {mins:02d}:{secs:02d}"
        cd_color = "#FF6666" if time_left < 60 else "#888888"
        self._set("countdown", self.countdown_label, cd_text, cd_color)

        atr       = signals.get('atr', 0.0)
        z_score   = signals.get('z_score', 0.0)
        rsi       = signals.get('rsi', 0.0)
        ev        = signals.get('ev', 0.0)
        macd      = signals.get('macd', {})
        hist      = macd.get('histogram', 0.0)
        direction = signals.get('signal_direction', 'NEUTRAL')
        trend     = signals.get('prob_trend', '─')
        market_p  = signals.get('p_win_estimate', 0.5)
        strike    = signals.get('strike_price', 0.0)
        atr_dist  = signals.get('atr_distance', 0.0)

        z_color   = "#FF4444" if abs(z_score) >= Z_SCORE_THRESHOLD else "white"
        rsi_color = "#FF4444" if rsi > 70 else ("#00CC88" if rsi < 30 else "white")
        dir_color = "#00FFAA" if direction == "UP" else ("#FF4444" if direction == "DOWN" else "gray")
        
        # ATR Distance Color: Green if comfortably above strike, white if slightly above, red if below
        if atr_dist > 1.0:
            dist_color = "#00CC88"
        elif atr_dist < 0:
            dist_color = "#FF4444"
        else:
            dist_color = "white"

        self._set("atr",      self.atr_val,    f"${atr:,.2f}")
        self._set("zscore",   self.zscore_val, f"{z_score:,.2f}",   z_color)
        self._set("rsi",      self.rsi_val,    f"{rsi:.1f}",         rsi_color)
        self._set("macd",     self.macd_val,   f"{hist:+.4f}",       "#00CC88" if hist > 0 else "#FF4444")
        self._set("ev",       self.ev_val,     f"{ev:+.4f}",         "#00CC88" if ev > 0 else "white")
        self._set("prob",     self.prob_val,   f"{market_p:.0%}")
        self._set("dir",      self.dir_val,    direction,            dir_color)
        self._set("trend",    self.ev_trend,   trend,
                  "#00CC88" if trend == "▲" else ("#FF4444" if trend == "▼" else "gray"))
        self._set("strike",   self.strike_val, f"${strike:,.2f}")
        self._set("atr_dist", self.atr_dist_val, f"{atr_dist:+.2f} ATR", dist_color)

        # Walls — only rewrite textbox when content changed
        supports: List[tuple] = signals.get('supports', [])
        resistances: List[tuple] = signals.get('resistances', [])
        walls_str = "".join(f"RESIST  {p:.2f}  |  ${v:,.0f}\n" for p, v in resistances[:5])
        walls_str += "─" * 30 + "\n"
        walls_str += "".join(f"SUPPORT {p:.2f}  |  ${v:,.0f}\n" for p, v in supports[:5])
        if walls_str != self._walls_cache:
            self._walls_cache = walls_str
            self.walls_text.configure(state="normal")
            self.walls_text.delete("1.0", "end")
            self.walls_text.insert("end", walls_str)
            self.walls_text.configure(state="disabled")

        # Prime Setup banner — only update on state change
        is_prime = signals.get('is_good_setup', False)
        if is_prime:
            self.signal_label.configure(text="⚡ PRIME SETUP — ACT NOW", text_color="#00FFAA")
            self._set_explanation(True, ev=ev, z_score=z_score, direction=direction)
            if not self._last_prime:
                self._alert_sound()
                self._update_last_trade()
        else:
            self.signal_label.configure(text="Monitoring... Wait for edge.", text_color="gray")
            self._set_explanation(False)
        self._last_prime = is_prime

    def _set_explanation(self, is_prime: bool, ev: float = 0.0,
                         z_score: float = 0.0, direction: str = "NEUTRAL"):
        if is_prime:
            bet = "YES" if direction == "UP" else "NO"
            text = (
                f"BTC momentum ({direction}) diverges from Kalshi market price.\n"
                f"Edge: EV={ev:+.3f} per $1 risked.\n\n"
                f"ACTION: On Kalshi, open the current KXBTC15M market and place "
                f"a {bet} contract. Size $5–$20. Edge closes quickly — act now.\n"
                f"{'[DRY RUN: order logged, not placed]' if DRY_RUN else '[LIVE: order auto-submitted]'}"
            )
        else:
            text = (
                "Waiting for a statistical edge.\n\n"
                "PRIME SETUP fires when ALL are true:\n"
                "  • Z-Score ≥ 2.0 — BTC 2σ from 15m mean\n"
                "  • EV > 0 — momentum model beats market odds\n"
                "  • 2-of-3 vote: RSI + MACD + Z-Score agree on direction\n\n"
                "When it fires: bet YES (BTC up) or NO (BTC down) based on direction."
            )
        self.signal_explain.configure(state="normal")
        self.signal_explain.delete("1.0", "end")
        self.signal_explain.insert("end", text)
        self.signal_explain.configure(state="disabled")

    def _alert_sound(self):
        try:
            threading.Thread(target=lambda: (
                winsound.Beep(880, 150),
                winsound.Beep(1100, 150),
                winsound.Beep(1320, 200)
            ), daemon=True).start()
        except Exception:
            pass

    def _update_last_trade(self):
        sig = trade_logger.get_last_signal()
        if sig:
            self.last_trade_label.configure(
                text=f"Last: {sig['direction']} | EV {sig['ev']} | {sig['timestamp'][:19]}",
                text_color="#AAAAAA")

    def _toggle_on_top(self):
        """Toggles the always-on-top window attribute."""
        self._always_on_top = not self._always_on_top
        self.attributes("-topmost", self._always_on_top)
        if self._always_on_top:
            self._pin_btn.configure(text="📌 Always on Top: ON",
                                    fg_color="#1e3a2a", hover_color="#2a5a3a")
        else:
            self._pin_btn.configure(text="📌 Always on Top: OFF",
                                    fg_color="#3a1e1e", hover_color="#5a2a2a")

    # ── Tray / Lifecycle ──────────────────────────────────────────────────────
    def _setup_tray(self):
        if not TRAY_AVAILABLE:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Show", lambda: self.after(0, self.deiconify)),
            pystray.MenuItem("Quit", lambda: self.after(0, self.on_closing))
        )
        self._tray_icon = pystray.Icon(
            "KalshiBot", _make_tray_icon_image(),
            "Kalshi Quant Assistant", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def iconify(self):
        """Override to hide to tray instead of minimizing."""
        if TRAY_AVAILABLE and self._tray_icon:
            self.withdraw()
        else:
            super().iconify()

    def on_closing(self):
        self.is_running = False
        if self._tray_icon:
            self._tray_icon.stop()
        self.destroy()
