from __future__ import annotations

import unittest

import pandas as pd

from config import settings
from strategy import evaluate_prepared_symbol


class StrategyScoringTests(unittest.TestCase):
    def test_near_zero_macd_cannot_explode_score(self):
        rows = 80
        frame = pd.DataFrame({
            "Close": [100.0] * (rows - 2) + [100.5, 101.0],
            "High": [101.0] * rows, "Volume": [2_000_000.0] * rows,
            "avg_volume": [1_000_000.0] * rows, "atr": [2.0] * rows,
            "ema_fast": [99.0] * (rows - 2) + [99.1, 99.2],
            "ema_slow": [98.0] * rows,
            "macd": [1e-12] * rows, "macd_signal": [0.0] * rows,
            "macd_hist": [1e-12] * (rows - 2) + [1e-10, 1e-6],
            "relative_strength": [0.20] * rows, "momentum_5": [0.20] * rows,
            "bb_upper": [110.0] * rows,
        })
        candidate = evaluate_prepared_symbol("ABC", frame, settings)
        self.assertIsNotNone(candidate)
        total_positive_weight = sum([
            settings.score_weight_relative_strength, settings.score_weight_macd_strength,
            settings.score_weight_macd_acceleration, settings.score_weight_ema_distance,
            settings.score_weight_ema_slope, settings.score_weight_volume,
            settings.score_weight_price_momentum, settings.score_weight_breakout,
        ])
        self.assertLessEqual(candidate.score, total_positive_weight)


if __name__ == "__main__":
    unittest.main()
