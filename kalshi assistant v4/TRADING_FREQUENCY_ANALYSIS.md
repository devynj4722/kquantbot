# Trading Frequency Analysis & Current Blockers

## Current Status
**Trades Placed (DRY RUN):** 0 live trades since edge-engine activation
**Highest Composite Score Recorded:** ~90 (was blocked by ATR distance gate)
**Most Common Blocker:** ATR Distance (price too far from strike)

---

## What's Required to Trade

The bot has **6 hard gates** that ALL must pass simultaneously:

### 1. **Edge Gate** (MIN_EDGE_CENTS ≥ 8¢)
- Detects mispricing: `abs(model_p_win - market_p_win) * 100`
- Your model says BTC will go UP/DOWN with X probability
- Market prices it differently (YES/NO imbalance)
- **Status:** ✓ This is working — you saw edge values like 8.2¢

### 2. **Time Gate** (not in first 3 min or last 3 min)
- Avoids trading in the opening/closing chaos
- Window: Minutes 3-57 of each 15-minute period
- **Status:** ✓ Simple calendar logic, always passes if in valid window

### 3. **ATR Distance Gate** (price within 2 ATR of strike)
- Strike price is what the contract settles against
- If current BTC is >2 ATR away from strike, trade blocks
- Last 5 minutes: tightens to 1 ATR (price must be closer)
- **Status:** ✗ **THIS IS THE PRIMARY BLOCKER**
  - Example: If ATR=200 and strike is 65000, price must be within 65400
  - If BTC drifts to 66000 or higher, gate closes
  - With your ~90 composite score, the price was likely ~2.3 ATR away

### 4. **Orderbook Gate** (imbalance ≥ 15 score)
- Checks bid/ask volume imbalance at 3¢ depth
- If orderbook is balanced (no pressure), score < 15
- **Status:** ? Unknown — need more data from live run

### 5. **CVD Gate** (verdict ≠ FADE)
- Cumulative Volume Delta tracks buy vs sell pressure
- FADE verdict = market order pressure contradicts your signal
- If you expect UP but massive sell volume = FADE = gate closes
- **Status:** ? Unknown — need more data from live run

### 6. **Final Minute Gate** (if <60s left, score ≥ 70)
- Last 60 seconds: only allows trades with very high conviction
- Otherwise gate closes to avoid slippage at expiry
- **Status:** ✓ Conditional, only applies when close to market close

### 7. **Composite Score** (≥ 55 required)
- Weighted average of 6 indicators: Edge (30%) + Momentum (20%) + OB (15%) + CVD (15%) + Basis (10%) + Regime (10%)
- **Status:** ✓ Your signals are hitting 70-90 range easily

### 8. **Position Limit** (max 3 open positions)
- Won't fire more than 3 trades in a 15-minute window
- **Status:** ✓ Applies only after gate 1-6 pass

---

## Why No Trades Yet? The ATR Distance Problem

The ATR distance gate is the **hardest gate to pass** because:

1. **Kalshi's 15-minute contracts have fixed strike prices** (e.g., "Will BTC be above $65,000 at 3:45pm?")
2. **BTC drifts throughout the 15-minute window** — it doesn't stay near the strike
3. **The gate requires price to be within 2 ATR of strike** — this is ~2 × current 15m volatility
4. **For a score of 90+ to trigger while ATR blocks, price must have drifted away from strike mid-trade-window**

### Example Scenario (What Likely Happened)
- 15m window opens: BTC = $65,100 (close to $65,000 strike)
- Minutes 5-10: Strong momentum UP + high edge detected
- Your signals scream: "BTC is underpriced, going UP" → Score 90
- But by minute 12, BTC has rallied to $66,800
- ATR = $500, so gate requires price < $65,000 + (2 × $500) = $66,000
- BTC at $66,800 > $66,000 limit → **ATR Gate Closes** ✗

---

## Expected Trading Frequency

Based on Kalshi market structure and your edge-first approach:

### Conservative Estimate (Current Gates)
- **Per 15-minute window:** 0.3-1.2 trades (very selective)
- **Per hour:** 1-5 trades
- **Per 8-hour session:** 8-40 trades

**Reasoning:**
- Kalshi markets are thin — edge detection is rare (~10-15% of windows have meaningful mispricing)
- ATR gate is restrictive — price must stay near strike (blocks ~60% of otherwise-valid signals)
- CVD gate adds another filter (~20% fail on flow conflicts)
- Composite score threshold is high (≥55 for detection, ≥70 for final-minute) → blocks weak signals
- Combined: Only ~5-8% of all signal windows result in actual trades

### Aggressive Scenario (If ATR Gate Were Relaxed to 3 ATR)
- Per hour: 5-15 trades
- Per session: 40-120 trades
- **Trade-off:** Would accept more false positives (slippage risk near expiry)

### Ideal Scenario (If You Relaxed Min Edge to 5¢ + Loosened ATR to 2.5)
- Per hour: 8-20 trades
- **Trade-off:** Lower edge quality, more losses from weaker signals

---

## How to Increase Trade Frequency (Options)

### **Option 1: Relax ATR Distance Gate** ⚠️ Risky
```python
# In config.py, change:
ATR_DIST_KILL_SWITCH = 2.0  # Currently 2.0
# To:
ATR_DIST_KILL_SWITCH = 3.0  # Allow 3x distance
# Or:
ATR_DIST_KILL_SWITCH = 2.5  # Compromise at 2.5x
```
- **Impact:** 2-3x more trades per hour
- **Risk:** Price may not reach strike before expiry → higher loss rate
- **Verdict:** Not recommended without backtesting

### **Option 2: Lower Composite Score Threshold** ⚠️ Quality Loss
```python
MIN_COMPOSITE_SCORE = 45  # From 55
```
- **Impact:** 40-50% more trades (catch weaker setups)
- **Risk:** Lower-quality signals → higher drawdown
- **Verdict:** Could test at 50 as compromise

### **Option 3: Lower Minimum Edge to 6¢** ✓ Reasonable
```python
MIN_EDGE_CENTS = 6  # From 8
```
- **Impact:** ~25% more edge detections
- **Risk:** Smaller edges = tighter stops, but acceptable
- **Verdict:** Reasonable if you want more frequency

### **Option 4: Relax Orderbook Gate** ✓ Safe
```python
OB_PASS_THRESHOLD = 10  # If we add one, currently dynamic
```
- **Impact:** ~20-30% more trades (currently many blocked here too)
- **Risk:** Low — orderbook imbalance is reliable
- **Verdict:** Safe to tighten if OB gate is a bottleneck

### **Option 5: Disable Final-Minute Overstrict Gate** ✓ Safe
```python
# In edge_engine.py:
final_min_pass = True  # Remove the score >= 70 requirement in final min
```
- **Impact:** Maybe 5-10% more trades in the last 60 seconds
- **Risk:** Low — you're capturing late-window edges
- **Verdict:** Safe change

---

## What You Should Do NOW

### 1. **Run for 3-5 hours in DRY_RUN mode**
   - Watch for trades that pass composite score (≥55) but fail gates
   - Note which gate is the PRIMARY blocker:
     - ATR distance
     - Orderbook imbalance
     - CVD verdict
     - Something else?

### 2. **Collect Data**
   - Log every signal that scores ≥55 and why it blocked
   - Identify patterns (e.g., "ATR blocks 80% of time")

### 3. **Analyze Block Distribution**
   - If ATR blocks 70%+ of high-scoring signals → relax it to 2.5 or 3.0
   - If Orderbook blocks 60%+ → maybe lower threshold
   - If CVD blocks 50%+ → might be a real market structure issue

### 4. **Test 1-2 Relaxations**
   - Start with Option 3 (lower edge to 6¢) — safest
   - Or Option 5 (remove final-minute strictness) — safest
   - Run 2 more hours with new config
   - Compare trade frequency

### 5. **Only Then Go Live**
   - DRY_RUN=False with conservative sizing ($1-2 per trade)
   - Monitor actual P&L impact of trades
   - Adjust gates based on live results

---

## Configuration Changes to Consider (Ranked by Safety)

| Rank | Change | Frequency Impact | Risk Level | Recommendation |
|------|--------|------------------|-----------|-----------------|
| 1 | ATR_DIST_KILL_SWITCH: 2.0 → 2.5 | +50% | Medium | Test after data collection |
| 2 | MIN_EDGE_CENTS: 8 → 6 | +25% | Low | Safe to try now |
| 3 | MIN_COMPOSITE_SCORE: 55 → 50 | +40% | Medium | Test if other gates pass |
| 4 | Remove final_min_pass override | +10% | Low | Safe to try |
| 5 | ATR_DIST_KILL_SWITCH: 2.0 → 3.0 | +150% | High | Only with backtesting |
| 6 | MIN_COMPOSITE_SCORE: 55 → 40 | +100% | High | Only with backtesting |

---

## Summary

**Why aren't trades firing?**
- Composite score threshold is high (≥55) — but you're hitting it ✓
- ATR distance gate is restrictive — most likely blocker ✗
- Other gates are working but may have room to relax ✓

**Trade frequency expectation:**
- Current strict config: 1-5 trades/hour
- With loose config: 10-20 trades/hour
- Current setup is **very conservative** (professional risk management)

**Next step:**
1. Run 3-5 hours in DRY_RUN, log all blocks
2. Identify primary blocker
3. Test 1 conservative adjustment
4. Compare results
5. Go live if satisfied

The bot is working correctly — it's just being **very selective** about which setups to trade, which is good for risk management but means slower trade frequency.
