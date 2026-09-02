import unittest
from datetime import date, timedelta

from goratio.dataset import prepare_market_data
from goratio.providers import RawMarketData, SINA_METADATA


class DatasetTests(unittest.TestCase):
    def test_prepared_dataset_reports_actual_span_and_quality_audit(self) -> None:
        start = date(2018, 12, 31)
        dates = [start + timedelta(days=index) for index in range(1830)]
        gold = tuple(
            {"date": trading_date.isoformat(), "close": 1800 + index / 10}
            for index, trading_date in enumerate(dates)
        )
        oil = tuple(
            {
                "date": trading_date.isoformat(),
                "close": -1 if index == 10 else 70 + index / 1000,
            }
            for index, trading_date in enumerate(dates)
        )
        raw = RawMarketData(
            source=SINA_METADATA,
            gold_records=gold,
            oil_records=oil,
            retrieved_at=None,  # prepare_market_data 不依赖获取时刻
        )

        result = prepare_market_data(
            raw,
            period="5y",
            completed_before=dates[-1] + timedelta(days=1),
            provenance="online",
            cache_stale=False,
        )

        self.assertEqual(result.actual_period[1], dates[-1].isoformat())
        self.assertGreaterEqual(result.span_days, 1825)
        self.assertGreaterEqual(result.observation_count, 1000)
        self.assertTrue(result.evidence_eligible)
        self.assertEqual(result.quality_status, "degraded")
        self.assertEqual(result.oil.audit.non_positive, 1)

    def test_short_history_keeps_prices_but_disables_evidence(self) -> None:
        raw = RawMarketData(
            source=SINA_METADATA,
            gold_records=(
                {"date": "2023-01-02", "close": 1800},
                {"date": "2024-01-02", "close": 1900},
            ),
            oil_records=(
                {"date": "2023-01-02", "close": 75},
                {"date": "2024-01-02", "close": 80},
            ),
            retrieved_at=None,
        )

        result = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2024, 1, 3),
            provenance="cache",
            cache_stale=True,
        )

        self.assertEqual(result.observation_count, 2)
        self.assertFalse(result.evidence_eligible)
        self.assertEqual(result.quality_status, "insufficient_history")
        self.assertEqual(result.points[-1].ratio, 23.75)


if __name__ == "__main__":
    unittest.main()
