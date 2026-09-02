import unittest
from datetime import date, datetime, timezone

from goratio.dataset import prepare_market_data
from goratio.evidence_gates import run_v2_evidence_bundle, run_v2_horizon_gate
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


class EvidenceGateTests(unittest.TestCase):
    def test_short_history_returns_insufficient_for_horizon_gate(self) -> None:
        raw = _short_raw()
        data = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2024, 1, 4),
            provenance="cache",
            cache_stale=False,
        )

        result = run_v2_horizon_gate(data, horizon=63)

        self.assertEqual(result["protocol"], "goratio-2a-v1")
        self.assertEqual(result["evidence_status"], "insufficient_data")
        self.assertIn("gates", result)

    def test_bundle_has_three_horizons(self) -> None:
        raw = _short_raw()
        data = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2024, 1, 4),
            provenance="cache",
            cache_stale=False,
        )

        bundle = run_v2_evidence_bundle(data)

        self.assertEqual(set(bundle["horizons"]), {"63", "126", "252"})


if __name__ == "__main__":
    unittest.main()
