import unittest
from datetime import date, datetime, timezone, timedelta

from goratio.dataset import prepare_market_data
from goratio.providers import RawMarketData, SINA_METADATA
from goratio.protocol_v2 import factor_snapshot_variant_b
from goratio.regime import structure_stability_factor


def _prepare_with_ratios(ratios):
    start = date(2020, 1, 1)
    gold_records = []
    oil_records = []
    for index, ratio in enumerate(ratios):
        gold = 1000 + index * 0.1
        trading_date = (start + timedelta(days=index)).isoformat()
        gold_records.append({"date": trading_date, "close": gold})
        oil_records.append({"date": trading_date, "close": gold / ratio})
    raw = RawMarketData(
        source=SINA_METADATA,
        gold_records=tuple(gold_records),
        oil_records=tuple(oil_records),
        retrieved_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    return prepare_market_data(
        raw,
        period="10y",
        completed_before=date(2025, 1, 1),
        provenance="cache",
        cache_stale=False,
    )


class RegimeFactorTests(unittest.TestCase):
    def test_stable_series_reports_stable_state(self) -> None:
        ratios = [20 + (index % 7) / 100 for index in range(1000)]
        data = _prepare_with_ratios(ratios)

        stability = structure_stability_factor(data)

        self.assertTrue(stability["available"])
        self.assertEqual(stability["state"], "stable")
        self.assertIn("rolling_median_shift_z", stability["method"])

    def test_high_regime_shift_is_unstable_and_blocks_variant_b_trigger(self) -> None:
        ratios = [
            (20 + (index % 7) / 100 if index < 600 else 40 + (index % 7) / 100)
            for index in range(1000)
        ]
        data = _prepare_with_ratios(ratios)

        stability = structure_stability_factor(data)
        snapshot = factor_snapshot_variant_b(data)

        self.assertEqual(stability["state"], "unstable")
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["valuation"]["zone"], "high")
        self.assertEqual(
            snapshot["research_state"], "valuation_high_structure_unstable"
        )


if __name__ == "__main__":
    unittest.main()
