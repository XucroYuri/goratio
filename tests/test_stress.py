import unittest
from datetime import date, datetime, timezone

from goratio.dataset import prepare_market_data
from goratio.providers import RawMarketData, SINA_METADATA
from goratio.stress import tail_stress_report


def _raw_with_negative_oil():
    return RawMarketData(
        source=SINA_METADATA,
        gold_records=(
            {"date": "2020-01-02", "close": 1500},
            {"date": "2020-04-20", "close": 1700},
            {"date": "2020-05-01", "close": 1700},
        ),
        oil_records=(
            {"date": "2020-01-02", "close": 60},
            {"date": "2020-04-20", "close": -37.63},
            {"date": "2020-05-01", "close": 20},
        ),
        retrieved_at=datetime(2020, 6, 1, tzinfo=timezone.utc),
    )


class StressTests(unittest.TestCase):
    def test_negative_oil_in_analysis_window_is_reported_not_silently_lost(self) -> None:
        raw = _raw_with_negative_oil()
        data = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2020, 6, 1),
            provenance="cache",
            cache_stale=False,
        )

        report = tail_stress_report(raw, data)

        self.assertEqual(report["non_positive_event_count"], 1)
        event = report["events"][0]
        self.assertEqual(event["date"], "2020-04-20")
        self.assertTrue(event["in_analysis_window"])
        self.assertFalse(event["log_ratio_defined"])
        self.assertTrue(event["protocol_1a_excluded"])
        self.assertIn("v2_handling", event)

    def test_stress_report_without_negative_events_is_empty(self) -> None:
        raw = RawMarketData(
            source=SINA_METADATA,
            gold_records=({"date": "2020-01-02", "close": 1500},),
            oil_records=({"date": "2020-01-02", "close": 60},),
            retrieved_at=datetime(2020, 6, 1, tzinfo=timezone.utc),
        )
        data = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2020, 6, 1),
            provenance="cache",
            cache_stale=False,
        )

        report = tail_stress_report(raw, data)

        self.assertEqual(report["non_positive_event_count"], 0)
        self.assertEqual(report["events"], [])


if __name__ == "__main__":
    unittest.main()
