# Integration Test Plan: Edge-First Trading System

## Pre-Test Checklist
- [x] All Python modules compile successfully
- [x] Config weights sum to 1.0 (verified: 0.30 + 0.20 + 0.15 + 0.15 + 0.10 + 0.10 = 1.0)
- [x] EdgeEngine has all 9 required methods
- [x] trades.csv header has 17 columns
- [x] DRY_RUN=True (no real orders will be placed)

## Phase 1: Raw Data Flow (First 2-3 signals)
Monitor these signals in the terminal and GUI:

### Expected Edge Engine Calculations
1. **Edge Detection (calculate_edge)**
   - model_p_win should vary ±5-15¢ from market price
   - edge_direction should toggle between YES_UNDERPRICED, NO_UNDERPRICED, FAIR
   - edge_cents should be in range [0, 50] for typical conditions

2. **Orderbook Imbalance (calculate_orderbook_imbalance)**
   - imbalance_ratio should show bid/ask volume at 3¢ depth
   - expected range: 0.5-2.5 (neutral ~1.0)
   - imbalance_direction: YES_PRESSURE / NO_PRESSURE / NEUTRAL

3. **Regime Detection (detect_regime)**
   - regime should be one of: SQUEEZE, EXPANSION, TRENDING, CHOPPY
   - time_remaining should decrease as market approaches expiry
   - status should indicate market phase (EARLY, PRIME, LATE, FINAL_MINUTE)

### Test Points
- [ ] `edge_cents` shows non-zero values (should NOT all be 0)
- [ ] `edge_direction` changes dynamically between YES/NO/FAIR
- [ ] `regime` changes at least once during a 15-minute window
- [ ] Terminal logs show "Phase 1: Raw indicators" message (check data_ingestion.py)

---

## Phase 2: Composite Scoring
Monitor the weighted score calculation:

### Component Scores (Each should be 0-100)
- [ ] `_score_edge`: Varies based on edge magnitude vs MIN_EDGE_CENTS (8¢) and STRONG_EDGE_CENTS (15¢)
- [ ] `_score_momentum`: High when RSI, MACD, and Z-score align bullishly/bearishly
- [ ] `_score_orderbook`: High when imbalance_ratio > IMBALANCE_STRONG (2.5)
- [ ] `_score_cvd`: High when CVD confirms momentum (CONFIRM verdict)
- [ ] `_score_basis`: High when basis divergence > BASIS_MIN_DIVERGENCE (8%)
- [ ] `_score_regime`: High when time decay aligns with regime

### Composite Score Calculation
- [ ] `composite_score` ranges 0-100
- [ ] No component dominates (all 6 weights are non-zero)
- [ ] Score correlates with `should_trade` flag (if score > MIN_COMPOSITE_SCORE=55, should_trade=True, assuming gates pass)

### Test Points
- [ ] At least 3 signals have score between 40-70 (mid-range zone)
- [ ] At least 1 signal has score > 70 (high-conviction setup)
- [ ] `should_trade` is False when composite < 55
- [ ] All 6 component scores are logged (check CSV)

---

## Phase 3: Trade Gating
Verify hard gates are working correctly:

### Expected Gates
- [ ] **edge_pass**: True if edge_cents >= MIN_EDGE_CENTS (8)
- [ ] **time_pass**: True if time_left > MIN_TIME_LEFT (5 minutes typical)
- [ ] **atr_pass**: True if ATR distance < ATR_DIST_KILL_SWITCH (2.0)
- [ ] **ob_pass**: True if orderbook is valid (has bids/asks within depth)
- [ ] **cvd_pass**: True if CVD is CONFIRM or NEUTRAL (False if FADE)
- [ ] **final_min_pass**: True if time_left > 60 seconds (for final minute handling)

### Test Points
- [ ] At least one signal has `edge_pass=False` (edge too small)
- [ ] No "unexpected None keys" in CSV (check for phantom columns)
- [ ] Gates description in GUI shows status: E(+/-), T(+/-), A(+/-), O(+/-), C(+/-), F(+/-)
- [ ] `cvd_verdict` explicitly shows CONFIRM, FADE, or NEUTRAL

---

## Phase 4: Smart Sizing
Verify position sizing scales correctly:

### Size Formula: calculate_smart_size(edge_cents, atr, time_left, regime, composite_score, hedge_factor)
- Base: $3.00
- Edge adjustment: ±0.5x if edge_cents > STRONG_EDGE_CENTS (15)
- ATR adjustment: 0.8x if ATR > 2.5
- Time decay: 1.0x (EARLY) → 1.3x (PRIME) → 1.0x (LATE) → 0.5x (FINAL_MINUTE)
- Regime adjustment: 0.7x (SQUEEZE), 1.0x (EXPANSION/TRENDING), 0.8x (CHOPPY)
- Hedge reduction: Multiply by hedge_factor (0.5-1.0) if net long exposure
- **Final range must stay [1.0, 5.0]**

### Test Points
- [ ] `smart_size` ranges [1.0, 5.0] across all signals
- [ ] Larger sizes when composite_score > 70 AND regime = EXPANSION
- [ ] Smaller sizes when regime = SQUEEZE or hedge_factor < 1.0
- [ ] Size printed in CSV `size_dollars` column

---

## Phase 5: Order Placement
Verify DRY_RUN logging and actual async placement:

### DRY_RUN Expected Behavior
- Terminal shows: `[DRY RUN] {SIDE} {contracts}x @ {limit_price}¢ on {ticker} | ${size} risk | Score {score} | {setup_type}`
- No actual HTTP POST to Kalshi
- CSV row added with `dry_run=True`

### Test Points
- [ ] At least 2 signals trigger trade placement (DRY_RUN logs appear)
- [ ] Each placement logs: side, contracts, price, ticker, setup_type
- [ ] `setup_type` is one of: CVD_DIVERGENCE, MOMENTUM_TREND, EDGE_MISPRICING, OB_COMPRESSION, BASIS_ARBITRAGE, REGIME_ALIGNED
- [ ] CSV row includes `dry_run=True` for logged trades

---

## Phase 6: CSV Logging & Reconciliation
Verify all new trades are logged with correct fields:

### Expected Fields (17 total)
```
timestamp, ticker, direction, ev, edge_cents, z_score, rsi,
macd_histogram, market_p_win, yes_price, kci, composite_score,
setup_type, size_dollars, dry_run, outcome, pnl_est
```

### Test Points
- [ ] New rows appear in trades.csv after each trade signal
- [ ] `timestamp` is ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
- [ ] `edge_cents` populated (should NOT be blank)
- [ ] `composite_score` populated and in range [0, 100]
- [ ] `setup_type` is non-empty string
- [ ] `size_dollars` in range [1.0, 5.0]
- [ ] `dry_run` is "True" (string, not boolean)
- [ ] `outcome` is "PENDING" for new rows
- [ ] No phantom None columns

---

## Phase 7: Settlement Reconciliation
Verify async reconciliation task fires when markets settle:

### Expected Behavior (After Market Expiry)
- Every 30-60 seconds, bot polls Kalshi `/markets/{ticker}` endpoint
- Retrieves settlement status from API response
- Updates trades.csv with `outcome` (WIN/LOSS/PUSH) and `pnl_est`
- Terminal logs: `Reconciling KXBTC15M-26MAR... → WIN, +$2.35`

### Test Points
- [ ] Terminal shows reconciliation logs (may take 1-2 minutes after market close)
- [ ] At least one completed market has outcome != PENDING
- [ ] `pnl_est` is populated with numeric value (positive for WIN, negative for LOSS)
- [ ] `outcome` changed from PENDING to WIN/LOSS/PUSH

---

## GUI Display Verification

### Column 1 (Left Panel)
- [ ] **15m ATR**: Shows current ATR value
- [ ] **RSI**: Shows RSI(14) 0-100
- [ ] **EV**: Shows expected value (should be ~0.02-0.05 for favorable trades)
- [ ] **Direction**: Shows BTC momentum (UP/DOWN/NEUTRAL)
- [ ] **Composite**: Shows composite_score 0-100 (was previously KCI)
- [ ] **Setup**: Shows setup_type (was previously Tier B/A)
- [ ] **Gates**: Shows E/T/A/O/C gates with +/- status

### Column 2 (Center Panel)
- Orderbook volume and spread

### Column 3 (Right Panel)
- [ ] **Z-Score**: Shows current Z-score
- [ ] **MACD Hist**: Shows MACD histogram value
- [ ] **Edge (¢)**: Shows edge_cents with direction (was YES_PROB)
- [ ] **Strike**: Current market price
- [ ] **Regime**: Shows regime + time_phase (was ATR_DIST)
- [ ] **OI**: Open Interest percentage
- [ ] **OB Imbalance**: Shows ratio + direction (was W-Score)

### Signal Banner (Top of GUI)
- [ ] When `should_trade=True`: Shows "MISPRICED CONTRACT (setup_type | score)" with component breakdown
- [ ] When `should_trade=False`: Shows blocked reason (e.g., "Edge < 8¢", "CVD FADE", "Score < 55")
- [ ] Banner updates every data_ingestion cycle

---

## Success Criteria

### Minimum Requirements (Trade System Works)
- ✓ Edge calculations appear in 3+ signals
- ✓ Composite scores calculated and logged in CSV
- ✓ At least 1 trade placement (DRY_RUN logged)
- ✓ trades.csv has 17 clean columns
- ✓ No Python errors in terminal (all modules importable)

### Desired Outcomes (System Optimized)
- ✓ Composite scores vary 30-90 range (not all 50-60)
- ✓ Setup types show variety (not just one type repeated)
- ✓ Gates block at least 2 signals (showing gate logic works)
- ✓ Smart sizing ranges 1.5-4.5 (using full allocation range)
- ✓ Regime changes at least once (showing regime detector works)
- ✓ Settlement reconciliation fires and updates outcomes

### Red Flags (Stop & Debug)
- ✗ All composite scores are identical
- ✗ `edge_cents` always zero or blank
- ✗ `should_trade` never becomes True
- ✗ CSV parsing fails (phantom columns or None keys)
- ✗ Setup types are always "UNKNOWN" or empty
- ✗ Smart sizes outside [1.0, 5.0] range
- ✗ ModuleNotFoundError for edge_engine

---

## Test Execution Steps

1. **Verify config is correct**
   ```bash
   cd /sessions/inspiring-clever-faraday/mnt/kalshi\ assistant\ v4
   python3 -c "from config import *; print(f'DRY_RUN={DRY_RUN}, MIN_COMPOSITE_SCORE={MIN_COMPOSITE_SCORE}')"
   ```

2. **Start the bot (let it run for 5+ minutes)**
   ```bash
   python3 main.py
   ```

3. **Monitor terminal output** for:
   - Phase 1/2/3/4 pipeline messages
   - DRY RUN order placement logs
   - No exceptions or import errors

4. **Monitor GUI** (if open in separate terminal):
   - Watch metrics update in real-time
   - Check that component scores appear in signal banner

5. **Check trades.csv** after 5 minutes:
   ```bash
   tail -5 trades.csv | cut -d, -f1,2,5,12,13,14,15,16
   # Should show: timestamp, ticker, edge_cents, composite_score, setup_type, size_dollars, dry_run, outcome
   ```

6. **Verify no CSV corruption**:
   ```bash
   python3 -c "import csv; f = csv.DictReader(open('trades.csv')); rows = list(f); print(f'Rows: {len(rows)}, No phantom keys: {all(None not in r for r in rows)}')"
   ```

---

## Notes for This Session

- **Weights are balanced**: Edge(30%) + Momentum(20%) + OB(15%) + CVD(15%) + Basis(10%) + Regime(10%) = 100%
- **Conservative sizing**: All positions $1-5 per trade
- **DRY_RUN safety**: No real orders placed unless DRY_RUN=False AND all gates pass
- **CVD gate is critical**: FADE verdict blocks trades even if other metrics align
- **Regime context matters**: SQUEEZE regime reduces size, EXPANSION increases it
- **Time decay is aggressive**: FINAL_MINUTE cuts size 50% to avoid slippage at expiry
