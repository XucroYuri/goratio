import unittest
from datetime import date, datetime, timezone

from goratio.data import AlignedPoint
from goratio.dataset import prepare_market_data
from goratio.providers import RawMarketData, SINA_METADATA
from goratio.tradability import (
    build_tradability_report,
    next_close_gap_summary,
    ratio_trade_expression,
    scan_non_positive_events,
)


def positive_raw() -> RawMarketData:
    return RawMarketData(
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


def raw_with_negative_oil() -> RawMarketData:
    raw = positive_raw()
    oil = list(raw.oil_records) + [
        {"date": "2020-04-20", "close": -37.63},
        {"date": "2020-04-21", "close": 0.0},
    ]
    return RawMarketData(
        source=raw.source,
        gold_records=raw.gold_records,
        oil_records=tuple(oil),
        retrieved_at=raw.retrieved_at,
    )


class TradabilityTests(unittest.TestCase):
    def test_negative_oil_events_are_not_silently_lost(self) -> None:
        events = scan_non_positive_events(raw_with_negative_oil())

        self.assertEqual(len(events), 2)
        self.assertTrue(all(event.instrument == "oil" for event in events))
        self.assertEqual(events[0].date, "2020-04-20")
        self.assertEqual(events[0].close, -37.63)

    def test_ratio_trade_expression_uses_contract_multipliers(self) -> None:
        expression = ratio_trade_expression(1900, 80)

        self.assertEqual(expression["ratio"], 23.75)
        self.assertEqual(expression["gold_contract_multiplier"], 100)
        self.assertEqual(expression["oil_contract_multiplier"], 1000)
        self.assertAlmostEqual(
            expression["cl_contracts_per_one_gc_notional"], 2.375
        )

    def test_next_close_gap_summary_handles_short_history(self) -> None:
        with self.subTest(short=True):
            summary = next_close_gap_summary([])
            self.assertEqual(summary["observation_count"], 0)
            self.assertIn("limitations", summary)

        with self.subTest(has_values=True):
            summary = next_close_gap_summary(
                (
                    AlignedPoint(
                        date=date(2024, 1, 2),
                        gold_close=100.0,
                        oil_close=10.0,
                        ratio=10.0,
                    ),
                    AlignedPoint(
                        date=date(2024, 1, 3),
                        gold_close=105.0,
                        oil_close=10.5,
                        ratio=10.0,
                    ),
                )
            )
            self.assertEqual(summary["observation_count"], 1)
            self.assertAlmostEqual(summary["median"], 0.048790164169432)

    def test_build_report_exposes_missing_execution_data_clearly(self) -> None:
        raw = positive_raw()
        data = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2024, 1, 4),
            provenance="cache",
            cache_stale=False,
        )

        report = build_tradability_report(raw, data)

        self.assertEqual(report["schema_version"], "goratio-tradability-v1")
        self.assertEqual(report["contracts"]["gold"]["contract_multiplier"], 100)
        self.assertEqual(report["contracts"]["oil"]["contract_multiplier"], 1000)
        self.assertFalse(report["renminbi_disclosure"]["usdcny_data_loaded"])
        self.assertIn("margin_proxy", report)
        self.assertIn("no_roll_calendar", report["risk_flags"])
        self.assertIn("不构成投资建议", report["disclaimer"])


    def test_renminbi_disclosure_accepts_usd_cny_without_entering_core(self) -> None:
        raw = positive_raw()
        data = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2024, 1, 4),
            provenance="cache",
            cache_stale=False,
        )

        report = build_tradability_report(raw, data, usd_cny=7.2)

        disclosure = report["renminbi_disclosure"]
        self.assertTrue(disclosure["usdcny_data_loaded"])
        self.assertAlmostEqual(disclosure["usd_cny"], 7.2)
        self.assertGreater(disclosure["gold_cny_per_troy_oz"], 0)
        self.assertGreater(disclosure["gold_cny_per_gram"], 0)
        self.assertGreater(disclosure["oil_cny_per_barrel"], 0)


if __name__ == "__main__":
    unittest.main()
