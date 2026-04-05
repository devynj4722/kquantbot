# Quick Start: New Edge-First Trading System

## Status: ✓ Ready to Test

All components verified:
- ✓ Config weights sum to 1.0
- ✓ EdgeEngine initialized with 9 methods
- ✓ trades.csv has 17 columns (no corruption)
- ✓ All imports successful (DRY_RUN mode safe)
- ✓ 8 historical trades loaded from CSV

## Run the Bot

```bash
cd "/sessions/inspiring-clever-faraday/mnt/kalshi assistant v4"
python3 main.py
```

**What happens:**
- Terminal: Real-time signal logs with edge/composite/setup data
- GUI window: Live metrics (if enabled in gui_display.py)
- trades.csv: New rows appended with every signal

**Safety**: DRY_RUN=True → No real orders placed, only logs

## Monitor These Outputs

### Terminal (Signal Flow)
```
[SIGNAL] KXBTC15M-26MAR151530-00
  Edge: +8.2¢ (YES_UNDERPRICED)
  Composite: 67.3 (EDGE_MISPRICING)
  Gates: E(✓) T(✓) A(✓) O(✓) C(✓) F(✓)
  Size: $2.50
  [DRY RUN] YES 250x @ 51¢ on KXBTC15M-26MAR151530-00 | $2.50 risk | Score 67.3 | EDGE_MISPRICING
```

### CSV (New Row Example)
```csv
2026-04-05T14:32:15Z,KXBTC15M-26MAR151530-00,UP,0.0621,8.2,2.0701,61.64,1.076131,0.51,0.51,,67.3,EDGE_MISPRICING,2.5,True,PENDING,
```

### GUI (Real-Time Display)
- **Composite**: 67.3 (was KCI)
- **Setup**: EDGE_MISPRICING (was Tier)
- **Edge**: +8.2¢ (new)
- **Gates**: E/T/A/O/C (was K-Switch A/E/T)
- **Regime**: EXPANSION, PRIME (new)

## What to Check During Testing

### First 5 Minutes
1. Edge values appear (should NOT be 0)
2. Composite scores vary 40-80 range
3. Setup types change (not always same type)
4. Gates block at least 1 signal

### After 15+ Minutes
1. At least 2-3 trades placed (DRY_RUN logs)
2. Regime changes (SQUEEZE ↔ EXPANSION)
3. trades.csv rows have all 17 fields
4. Sizes stay in [1.0, 5.0] dollar range

### Red Flags (Stop if You See)
- ✗ All edge values = 0
- ✗ All composite scores = 55
- ✗ CSV has blank columns
- ✗ ModuleNotFoundError (data_ingestion, edge_engine)
- ✗ All setup_type = "UNKNOWN"

## Config Reference

| Setting | Value | Purpose |
|---------|-------|---------|
| MIN_EDGE_CENTS | 8 | Minimum edge to consider trading |
| STRONG_EDGE_CENTS | 15 | Threshold for size-up |
| MIN_COMPOSITE_SCORE | 55 | Min composite to enter |
| W_EDGE | 30% | Edge weight in score |
| W_MOMENTUM | 20% | Momentum weight |
| W_ORDERBOOK | 15% | OB imbalance weight |
| W_CVD | 15% | CVD confirmation weight |
| W_BASIS | 10% | Basis arbitrage weight |
| W_REGIME | 10% | Regime alignment weight |
| DRY_RUN | True | Safety flag (no real orders) |
| TRADE_SIZE_DOLLARS | 5 | Max position size |

## File Structure

```
├── main.py                  # Entry point (starts bot loop)
├── config.py                # Config + env vars (DRY_RUN=True)
├── math_engine.py           # RSI, MACD, Z-score, ATR
├── edge_engine.py           # NEW: Edge scoring (8 functions)
├── data_ingestion.py        # WebSocket → 4-phase pipeline
├── trade_executor.py        # Order placement (async)
├── trade_logger.py          # CSV logging (17 columns)
├── gui_display.py           # Real-time metrics display
├── trades.csv               # Trade history (8 historical)
├── TEST_PLAN.md             # Full testing checklist
└── kci_state.json           # State broadcast to GUI
```

## Key Metrics in CSV

```
timestamp        - ISO 8601 (e.g., 2026-04-05T14:32:15Z)
ticker           - Kalshi contract ID
direction        - UP/DOWN
ev               - Expected value (0.02-0.05 typical)
edge_cents       - Mispricing in cents (0-50 typical)
z_score          - Statistical Z-score
rsi              - Relative Strength Index
macd_histogram   - MACD histogram value
market_p_win     - Market-implied probability
yes_price        - Order limit price
composite_score  - Weighted score 0-100 (NEW)
setup_type       - Signal type (NEW: 6 types)
size_dollars     - Position size $1-5 (NEW)
dry_run          - "True" = DRY_RUN mode
outcome          - PENDING / WIN / LOSS / PUSH
pnl_est          - Estimated P&L (after settlement)
```

## Next Steps

1. **Start bot**: `python3 main.py`
2. **Watch terminal** for 5+ minutes
3. **Check trades.csv** for new rows
4. **Review TEST_PLAN.md** for detailed validation
5. **(Optional)** Review trades.csv with pivot table to backtest

---

## Troubleshooting

**Q: No signals appearing?**
- Check Coinbase connection (WebSocket)
- Verify no Kalshi API errors in terminal
- Ensure MIN_EDGE_CENTS threshold isn't too high

**Q: All composite scores are 55?**
- Check EdgeEngine is initialized (should appear in first 30 seconds)
- Verify math_engine is providing non-zero indicators
- Check CVD data is flowing (should see cvd_confirm in logs)

**Q: Sizes always $1.00?**
- Check smart_size calculation (should vary 1.0-5.0)
- Verify edge_cents > STRONG_EDGE_CENTS (15) triggers size-up
- Check regime detection (SQUEEZE reduces size)

**Q: CSV parsing fails?**
- Run: `python3 -c "import csv; rows = list(csv.DictReader(open('trades.csv'))); print(f'Clean: {len(rows)} rows')")`
- If fails, check for phantom None keys

---

## Live Trading (When Ready)

To transition from DRY_RUN to live trading:

1. Change in config.py: `DRY_RUN = False`
2. Ensure API keys are in .env
3. Start with TRADE_SIZE_DOLLARS = 1 (test size)
4. Verify gates are all passing (E/T/A/O/C)
5. Watch first 5 orders execute on Kalshi

**⚠️ WARNING: Live trading will place REAL orders. Only set DRY_RUN=False after extensive testing.**
