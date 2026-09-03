import unittest
from datetime import date, datetime, timezone

from goratio.dataset import prepare_market_data
from goratio.formal_v2 import generate_v2_formal_report
from goratio.providers import RawMarketData, SINA_METADATA


def _short_raw():
    return RawMarketData(
        source=SINA_METADATA,
        gold_records=(
            {"date": "2024-01-02", "close": 2000},
            {"date": "2024-01-03", "close": 2010},
        ),
        oil_records=(
            {"date": "2024-01-02", "close": 100},
            {"date": "2024-01-03", "close": 101},
        ),
        retrieved_at=datetime(2024, 1, 4, tzinfo=timezone.utc),
    )


class FormalV2Tests(unittest.TestCase):
    def test_generate_v2_formal_report_returns_statuses(self) -> None:
        raw = _short_raw()
        data = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2024, 1, 4),
            provenance="cache",
            cache_stale=False,
        )

        report = generate_v2_formal_report(data)

        self.assertEqual(report["protocol"], "goratio-2a-v1")
        self.assertEqual(report["overall_status"], "insufficient_data")
        self.assertEqual(len(report["horizon_status"]), 3)


if __name__ == "__main__":
    unittest.main()
