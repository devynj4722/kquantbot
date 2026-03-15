import unittest
from math_engine import MathEngine

class TestMathEngine(unittest.TestCase):
    
    def setUp(self):
        self.engine = MathEngine()
        
    def test_ev_calculation(self):
        # EV = (P_win * Pot_Prof) - (P_loss * Pot_Loss)
        ev = self.engine.calculate_ev(p_win=0.6, pot_profit=1.5, pot_loss=1.0)
        # 0.6 * 1.5 - 0.4 * 1.0 = 0.9 - 0.4 = 0.5
        self.assertAlmostEqual(ev, 0.5)
        
    def test_orderbook_walls(self):
        # Below volume threshold (configured to 1000 in config.py usually, assuming it here)
        self.engine.update_orderbook('bid', 95000, 500)
        self.engine.update_orderbook('bid', 94000, 1500)
        self.engine.update_orderbook('ask', 96000, 2000)
        
        supports, resistances = self.engine.get_support_resistance_walls()
        
        # We expect 94000 to be the only support wall (vol >= 1000)
        self.assertEqual(len(supports), 1)
        self.assertEqual(supports[0][0], 94000)
        self.assertEqual(supports[0][1], 1500)
        
        # We expect 96000 to be a resistance wall
        self.assertEqual(len(resistances), 1)
        self.assertEqual(resistances[0][0], 96000)
        self.assertEqual(resistances[0][1], 2000)
        
    def test_atr_and_zscore(self):
        # We need ATR_PERIODS + 1 data points for ATR (default 15)
        # We simulate a completely flat market
        for i in range(20):
            self.engine.add_kline({
                'timestamp': i,
                'open': 100.0,
                'high': 105.0,
                'low': 95.0,
                'close': 100.0,
                'volume': 10
            })
            
        atr = self.engine.calculate_atr()
        z_score = self.engine.calculate_z_score(100.0)
        
        # TR should be 10 for all periods
        self.assertEqual(atr, 10.0)
        # Current price = mean price, so z_score should be 0.0
        self.assertEqual(z_score, 0.0)

if __name__ == '__main__':
    unittest.main()
