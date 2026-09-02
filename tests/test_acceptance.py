import io
import math
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from goratio.cache import CacheError, CacheStore, DataLoader
from goratio.cli import main
from goratio.dataset import prepare_market_data
from goratio.providers import (
    HTTPClientError,
    ProviderError,
    RawMarketData,
    SINA_METADATA,
    YahooProvider,
)
from goratio.research import run_research


def eligible_raw() -> RawMarketData:
    start = date(2018, 1, 1)
    gold_records = []
    oil_records = []
    for index in range(2200):
        trading_date = start + timedelta(days=index)
        gold = 1500 * math.exp(index / 20000)
        ratio = 25 + 4 * math.sin(index / 30)
        gold_records.append({"date": trading_date.isoformat(), "close": gold})
        oil_records.append(
            {"date": trading_date.isoformat(), "close": gold / ratio}
        )
    return RawMarketData(
        source=SINA_METADATA,
        gold_records=tuple(gold_records),
        oil_records=tuple(oil_records),
        retrieved_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
    )


class FixedProvider:
    metadata = SINA_METADATA

    def __init__(self, raw: RawMarketData) -> None:
        self.raw = raw

    def fetch(self, *, timeout: float = 10) -> RawMarketData:
        return self.raw


class RejectingClient:
    def __init__(self) -> None:
        self.timeout = None

    def get(self, url: str, timeout: float) -> str:
        self.timeout = timeout
        raise HTTPClientError("timed out")


class AcceptanceTests(unittest.TestCase):
    def test_fixed_snapshot_repeats_identical_research_result(self) -> None:
        raw = eligible_raw()
        data = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2025, 1, 1),
            provenance="user_csv",
            cache_stale=False,
        )

        first = run_research(
            data,
            event_bootstrap_repetitions=29,
            structural_bootstrap_repetitions=29,
        )
        second = run_research(
            data,
            event_bootstrap_repetitions=29,
            structural_bootstrap_repetitions=29,
        )

        self.assertEqual(first, second)

    def test_three_year_request_keeps_coverage_but_fails_five_year_gate(self) -> None:
        raw = eligible_raw()

        data = prepare_market_data(
            raw,
            period="3y",
            completed_before=date(2025, 1, 1),
            provenance="online",
            cache_stale=False,
        )

        self.assertGreater(data.observation_count, 1000)
        self.assertFalse(data.evidence_eligible)
        self.assertEqual(data.quality_status, "insufficient_history")

    def test_cache_hash_detects_price_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CacheStore(Path(directory))
            path = store.write(eligible_raw())
            content = path.read_text(encoding="utf-8").replace(
                '"close":1500.0', '"close":1501.0', 1
            )
            path.write_text(content, encoding="utf-8")

            with self.assertRaisesRegex(CacheError, "摘要校验失败"):
                store.load("cn_public")

    def test_yahoo_network_failure_is_bounded_and_actionable(self) -> None:
        client = RejectingClient()

        with self.assertRaisesRegex(ProviderError, "海外网络.*代理.*稍后重试"):
            YahooProvider(client=client).fetch(timeout=0.25)

        self.assertEqual(client.timeout, 0.25)

    def test_human_output_has_disclosures_without_directional_instructions(self) -> None:
        raw = eligible_raw()
        with tempfile.TemporaryDirectory() as directory:
            loader = DataLoader(
                cache=CacheStore(Path(directory)),
                providers={"cn_public": FixedProvider(raw)},
            )
            output = io.StringIO()
            exit_code = main(
                ["now", "--period", "5y"],
                loader=loader,
                today=lambda: date(2025, 1, 1),
                stdout=output,
                stderr=io.StringIO(),
            )

        rendered = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("数据来源", rendered)
        self.assertIn("价格口径", rendered)
        self.assertIn("方法局限", rendered)
        self.assertIn("不构成投资建议", rendered)
        for forbidden in ("建议买入", "建议卖出", "最优仓位", "保证收益"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
