import os
from typing import Dict, Any, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich import box
from config import KALSHI_TICKER, COINBASE_PRODUCT_ID, Z_SCORE_THRESHOLD

class UIDisplay:
    def __init__(self):
        self.console = Console()
        self.is_running = True

    def log_error(self, message: str):
        self.console.print(f"[bold red]Error[/bold red]: {message}")
        
    def log_info(self, message: str):
        self.console.print(f"[bold cyan]Info[/bold cyan]: {message}")

    def update_state(self, current_price: float, signals: Dict[str, Any]):
        """ Re-renders the terminal dashboard with the latest state. """
        # We clear the console to redraw the 'frame'
        os.system('cls' if os.name == 'nt' else 'clear')
        
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        layout["main"].split_row(
            Layout(name="metrics"),
            Layout(name="orderbook")
        )

        # Header
        header_text = f"[bold yellow]Kalshi Quant Assistant[/bold yellow] | [green]{COINBASE_PRODUCT_ID}[/green] : ${current_price:,.2f} | [blue]{KALSHI_TICKER}[/blue]"
        layout["header"].update(Panel(header_text, box=box.HEAVY))

        # Metrics Panel
        metrics_table = Table(show_header=False, box=box.SIMPLE)
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Value", justify="right")
        
        atr = signals.get('atr', 0.0)
        z_score = signals.get('z_score', 0.0)
        ev = signals.get('ev', 0.0)
        
        # Colorize Z-Score if it breaches threshold
        z_color = "red" if abs(z_score) >= Z_SCORE_THRESHOLD else "white"
        
        metrics_table.add_row("15m ATR", f"${atr:,.2f}")
        metrics_table.add_row("Z-Score", f"[{z_color}]{z_score:,.2f}[/{z_color}]")
        metrics_table.add_row("Expected Value (EV)", f"{ev:,.2f}")
        
        layout["metrics"].update(Panel(metrics_table, title="Statistical Edge", box=box.ROUNDED))

        # Orderbook / Walls Panel
        walls_table = Table(box=box.SIMPLE)
        walls_table.add_column("Type", style="bold")
        walls_table.add_column("Price Bucket", justify="right")
        walls_table.add_column("Volume", justify="right")
        
        supports: List[tuple] = signals.get('supports', [])
        resistances: List[tuple] = signals.get('resistances', [])
        
        # Show top 5 resistances
        for p, v in resistances[:5]:
            walls_table.add_row("[red]Resistance[/red]", f"${p:,.2f}", f"{v:,.0f}")
            
        walls_table.add_row("---", "---", "---")
        
        # Show top 5 supports
        for p, v in supports[:5]:
            walls_table.add_row("[green]Support[/green]", f"${p:,.2f}", f"{v:,.0f}")
            
        layout["orderbook"].update(Panel(walls_table, title="Kalshi Liquidity Walls", box=box.ROUNDED))

        # Footer / Trade Signal
        is_good_setup = signals.get('is_good_setup', False)
        if is_good_setup:
            footer_content = "[bold green blink]PRIME SETUP DETECTED - EVALUATE KALSHI STRIKE NOW[/bold green blink]"
        else:
            footer_content = "[white]Monitoring... Wait for edge.[/white]"
            
        layout["footer"].update(Panel(footer_content, box=box.HEAVY))

        self.console.print(layout)
