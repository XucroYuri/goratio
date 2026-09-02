import json
import unittest
from datetime import date, datetime, timezone

from goratio.cache import LoadedData
from goratio.dataset import prepare_market_data
from goratio.providers import RawMarketData, SINA_METADATA
from goratio.reporting import build_result
from goratio.research import run_research


class ReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = RawMarketData(
            source=SINA_METADATA,
            gold_records=(
                {"date": "2023-01-02", "close": 1800},
                {"date": "2024-01-02", "close": 1900},
            ),
            oil_records=(
                {"date": "2023-01-02", "close": 75},
                {"date": "2024-01-02", "close": 80},
            ),
            retrieved_at=datetime(2024, 1, 3, tzinfo=timezone.utc),
        )
        self.loaded = LoadedData(
            raw=self.raw,
            provenance="cache",
            cache_origin="user_csv",
            cache_age_hours=80.0,
            cache_stale=True,
            snapshot_sha256="a" * 64,
            warnings=("缓存已陈旧",),
        )
        self.prepared = prepare_market_data(
            self.raw,
            period="5y",
            completed_before=date(2024, 1, 4),
            provenance="cache",
            cache_stale=True,
        )

    def test_now_result_contains_public_contract_and_strict_json(self) -> None:
        result = build_result(self.loaded, self.prepared)

        self.assertEqual(result["schema_version"], "goratio-result-v1")
        self.assertEqual(result["as_of"], "2024-01-02")
        self.assertEqual(result["source"]["id"], "cn_public")
        self.assertEqual(result["actual_period"], ["2023-01-02", "2024-01-02"])
        self.assertEqual(result["observation_count"], 2)
        self.assertEqual(result["data_quality"]["status"], "insufficient_history")
        self.assertTrue(result["data_quality"]["cache"]["stale"])
        self.assertEqual(result["evidence_status"], {"overall": "not_evaluated"})
        json.dumps(result, allow_nan=False)

    def test_analysis_result_embeds_all_preregistered_statuses(self) -> None:
        research = run_research(
            self.prepared,
            event_bootstrap_repetitions=9,
            structural_bootstrap_repetitions=9,
        )

        result = build_result(self.loaded, self.prepared, research=research)

        self.assertEqual(len(result["evidence_status"]), 6)
        self.assertIn("conditional_forward_returns", result)
        self.assertIn("stability_diagnostic", result)
        self.assertIn("仅供历史统计研究", result["disclaimer"])


if __name__ == "__main__":
    unittest.main()
