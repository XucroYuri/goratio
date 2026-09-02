import json
import unittest
from datetime import date, datetime, timezone, timedelta

from goratio.dataset import prepare_market_data
from goratio.episode_study import (
    run_episode_evidence_bundle,
    run_episode_evidence_study,
)
from goratio.providers import RawMarketData, SINA_METADATA


def _raw_with_low_episodes() -> RawMarketData:
    start = date(2020, 1, 1)
    gold_records = []
    oil_records = []
    # More frequent low blocks give enough episodes to exercise split logic.
    low_blocks = [(300, 320), (500, 520), (700, 720), (900, 920)]
    for index in range(1100):
        ratio = 10 if any(a <= index < b for a, b in low_blocks) else 30
        gold = 1000 + index
        trading_date = (start + timedelta(days=index)).isoformat()
        gold_records.append({"date": trading_date, "close": gold})
        oil_records.append({"date": trading_date, "close": gold / ratio})
    return RawMarketData(
        source=SINA_METADATA,
        gold_records=tuple(gold_records),
        oil_records=tuple(oil_records),
        retrieved_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def _prepared():
    raw = _raw_with_low_episodes()
    return prepare_market_data(
        raw,
        period="10y",
        completed_before=date(2025, 1, 1),
        provenance="cache",
        cache_stale=False,
    )


class EpisodeStudyTests(unittest.TestCase):
    def test_single_horizon_returns_episode_based_oos_split(self) -> None:
        data = _prepared()

        result = run_episode_evidence_study(data, horizon=10)

        self.assertEqual(result["horizon_trading_days"], 10)
        self.assertIn("split_date", result)
        self.assertGreater(result["episode_count"], 0)
        self.assertIn("out_of_sample", result)
        self.assertIn("evidence_status", result)
        json.dumps(result, ensure_ascii=False, allow_nan=False)

    def test_bundle_contains_three_horizons(self) -> None:
        data = _prepared()

        bundle = run_episode_evidence_bundle(data)

        self.assertEqual(set(bundle["horizons"]), {"63", "126", "252"})
        for horizon in bundle["horizons"].values():
            self.assertIn("evidence_status", horizon)


if __name__ == "__main__":
    unittest.main()
