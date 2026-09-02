import unittest
from datetime import date, datetime, timezone, timedelta

from goratio.backtest import run_episode_cost_backtest
from goratio.dataset import prepare_market_data
from goratio.providers import RawMarketData, SINA_METADATA


def _raw_with_low_episodes_and_positive_gold_trend() -> RawMarketData:
    start = date(2020, 1, 1)
    gold_records = []
    oil_records = []
    blocks = [(300, 320), (600, 620), (900, 920)]
    for index in range(1100):
        ratio = 10 if any(a <= index < b for a, b in blocks) else 30
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
    raw = _raw_with_low_episodes_and_positive_gold_trend()
    return prepare_market_data(
        raw,
        period="10y",
        completed_before=date(2025, 1, 1),
        provenance="cache",
        cache_stale=False,
    )


class EpisodeCostBacktestTests(unittest.TestCase):
    def test_backtest_returns_net_trade_level_metrics(self) -> None:
        data = _prepared()

        report = run_episode_cost_backtest(
            data,
            horizon=10,
            round_trip_cost_bps=20.0,
        )

        self.assertGreater(report["trade_count"], 0)
        self.assertIn("metrics", report)
        self.assertIsNotNone(report["metrics"]["mean_net_return"])
        self.assertIn("trades", report)
        self.assertEqual(report["risk_gates"]["cost_adjusted_positive_passed"], True)
        self.assertIn("不构成投资建议", report["disclaimer"])

    def test_large_round_trip_cost_flips_risk_gate(self) -> None:
        data = _prepared()

        report = run_episode_cost_backtest(
            data,
            horizon=10,
            round_trip_cost_bps=10000.0,
        )

        self.assertFalse(report["risk_gates"]["cost_adjusted_positive_passed"])
        self.assertIn("negative_cost_adjusted_mean", report["risk_flags"])

    def test_short_history_returns_insufficient_trade_gate(self) -> None:
        raw = _raw_with_low_episodes_and_positive_gold_trend()
        data = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2020, 5, 1),
            provenance="cache",
            cache_stale=False,
        )

        report = run_episode_cost_backtest(data, horizon=10)

        self.assertEqual(report["trade_count"], 0)
        self.assertIn("insufficient_trade_count", report["risk_flags"])


    def test_t1_close_execution_uses_next_common_day_fill(self) -> None:
        data = _prepared()

        report = run_episode_cost_backtest(
            data,
            horizon=10,
            round_trip_cost_bps=20.0,
            t1_close_execution=True,
        )

        self.assertTrue(report["t1_close_execution"])
        self.assertGreaterEqual(report["trade_count"], 0)
        self.assertIn(
            "T+1 模式使用信号后一个共同交易日收盘价执行",
            report["limitations"][1],
        )


    def test_roll_cost_bps_is_included_in_net_return(self) -> None:
        data = _prepared()

        report = run_episode_cost_backtest(
            data,
            horizon=10,
            round_trip_cost_bps=20.0,
            roll_cost_bps=10.0,
        )

        self.assertEqual(report["roll_cost_bps"], 10.0)
        self.assertIsNotNone(report["metrics"]["mean_net_return"])


if __name__ == "__main__":
    unittest.main()
