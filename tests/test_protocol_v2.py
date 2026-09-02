import unittest
from datetime import date, datetime, timezone, timedelta

from goratio.dataset import prepare_market_data
from goratio.providers import RawMarketData, SINA_METADATA
from goratio.protocol_v2 import (
    PROTOCOL_V2_ID,
    PROTOCOL_V2_SPEC,
    build_protocol_list,
    factor_snapshot,
)


def _raw_with_low_current_ratio_and_positive_gold_momentum() -> RawMarketData:
    start = date(2020, 1, 1)
    gold_records = []
    oil_records = []
    for index in range(800):
        ratio = 10 if index >= 750 else 30
        gold = 1000 + index
        trading_date = (start + timedelta(days=index)).isoformat()
        gold_records.append({"date": trading_date, "close": gold})
        oil_records.append({"date": trading_date, "close": gold / ratio})
    return RawMarketData(
        source=SINA_METADATA,
        gold_records=tuple(gold_records),
        oil_records=tuple(oil_records),
        retrieved_at=datetime(2022, 6, 1, tzinfo=timezone.utc),
    )


class ProtocolV2Tests(unittest.TestCase):
    def test_spec_is_preregistered_draft_with_fixed_thresholds(self) -> None:
        self.assertEqual(PROTOCOL_V2_ID, "goratio-2a-v1")
        self.assertEqual(PROTOCOL_V2_SPEC["status"], "draft_preregistered")
        self.assertEqual(PROTOCOL_V2_SPEC["factors"][0]["low_threshold"], 0.2)
        self.assertEqual(
            PROTOCOL_V2_SPEC["factors"][0]["high_threshold"], 0.8
        )
        self.assertTrue(PROTOCOL_V2_SPEC["not_investment_advice"])

    def test_factor_snapshot_returns_low_value_positive_trend_trigger(self) -> None:
        raw = _raw_with_low_current_ratio_and_positive_gold_momentum()
        data = prepare_market_data(
            raw,
            period="10y",
            completed_before=date(2022, 12, 31),
            provenance="cache",
            cache_stale=False,
        )

        snapshot = factor_snapshot(data)

        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["research_state"], "positive_research_trigger")
        self.assertLess(snapshot["factors"]["F1_valuation"]["percentile"], 0.2)
        self.assertGreater(
            snapshot["factors"]["F2_trend_confirmation"]["gold_252d_momentum"],
            0,
        )

    def test_factor_snapshot_marks_short_history_unavailable(self) -> None:
        raw = _raw_with_low_current_ratio_and_positive_gold_momentum()
        data = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2020, 5, 1),
            provenance="cache",
            cache_stale=False,
        )
        # completed_before truncates history below 252d momentum source.
        snapshot = factor_snapshot(data)
        self.assertFalse(snapshot["available"])

    def test_protocol_list_includes_frozen_and_draft_v2(self) -> None:
        protocols = build_protocol_list()
        self.assertEqual(protocols[0], {"id": "goratio-1a-v1", "status": "frozen"})
        self.assertEqual(protocols[1]["id"], PROTOCOL_V2_ID)
        self.assertEqual(protocols[1]["status"], "draft_preregistered")


if __name__ == "__main__":
    unittest.main()
