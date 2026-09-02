import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from goratio.contracts import (
    ContractRecord,
    build_contract_series,
    contract_csv_to_raw_market_data,
    parse_contract_records,
)
from goratio.dataset import prepare_market_data


class ContractSeriesTests(unittest.TestCase):
    def test_roll_calendar_selects_new_contract_by_open_interest(self) -> None:
        records = [
            ContractRecord(
                date=date(2024, 1, 2), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2000.0,
                volume=100, open_interest=50,
            ),
            ContractRecord(
                date=date(2024, 1, 3), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2010.0,
                volume=80, open_interest=40,
            ),
            ContractRecord(
                date=date(2024, 1, 3), instrument="gold", symbol="GC",
                contract_month="2024-04", close=2020.0,
                volume=200, open_interest=300,
                open=2015.0, settle=2018.0,
            ),
        ]

        result = build_contract_series(records)

        series = result["series"]["gold"]["calendar"]
        self.assertEqual(series[0]["contract_month"], "2024-02")
        self.assertEqual(series[1]["contract_month"], "2024-04")
        self.assertEqual(len(result["roll_events"]), 1)
        roll = result["roll_events"][0]
        self.assertEqual(roll["old_contract"], "2024-02")
        self.assertEqual(roll["new_contract"], "2024-04")
        self.assertAlmostEqual(roll["roll_gap_bps"], (2020 / 2010 - 1) * 10000)

    def test_parse_contract_records_from_rows(self) -> None:
        rows = [
            {
                "date": "2024-01-02",
                "instrument": "oil",
                "symbol": "CL",
                "contract_month": "2024-03",
                "close": "75.5",
                "volume": "1000",
                "open_interest": "500",
                "open": "75.0",
                "settle": "75.6",
            }
        ]

        records = parse_contract_records(rows)

        self.assertEqual(records[0].contract_month, "2024-03")
        self.assertEqual(records[0].close, 75.5)
        self.assertEqual(records[0].volume, 1000.0)
        self.assertEqual(records[0].open, 75.0)
        self.assertEqual(records[0].settle, 75.6)


class ContractCsvBridgeTests(unittest.TestCase):
    def test_contract_csv_feeds_existing_prepare_market_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "combined.csv"
            path.write_text(
                "date,instrument,symbol,contract_month,close,volume,open_interest\n"
                "2024-01-02,gold,GC,2024-02,2000,100,50\n"
                "2024-01-03,gold,GC,2024-02,2010,80,40\n"
                "2024-01-03,gold,GC,2024-04,2020,200,300\n"
                "2024-01-02,oil,CL,2024-03,75,1000,500\n"
                "2024-01-03,oil,CL,2024-03,80,900,400\n"
                "2024-01-03,oil,CL,2024-05,85,1500,1000\n",
                encoding="utf-8",
            )
            raw = contract_csv_to_raw_market_data(path)
            data = prepare_market_data(
                raw,
                period="5y",
                completed_before=date(2024, 1, 4),
                provenance="user_contract_csv",
                cache_stale=False,
            )

        self.assertEqual(data.observation_count, 2)
        self.assertEqual(data.selected.points[-1].ratio, 2020 / 85)


class RollAdjustedSeriesTests(unittest.TestCase):
    def test_roll_adjusted_series_removes_contract_switch_jump(self) -> None:
        from goratio.contracts import build_roll_adjusted_series

        records = [
            ContractRecord(
                date=date(2024, 1, 2), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2000.0,
                volume=100, open_interest=50,
            ),
            ContractRecord(
                date=date(2024, 1, 3), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2010.0,
                volume=80, open_interest=40,
            ),
            ContractRecord(
                date=date(2024, 1, 3), instrument="gold", symbol="GC",
                contract_month="2024-04", close=2020.0,
                volume=200, open_interest=300,
                open=2015.0, settle=2018.0,
            ),
            ContractRecord(
                date=date(2024, 1, 4), instrument="gold", symbol="GC",
                contract_month="2024-04", close=2030.0,
                volume=250, open_interest=400,
            ),
        ]

        adjusted = build_roll_adjusted_series(records)
        calendar = adjusted["series"]["gold"]["calendar"]

        # 换月当天 raw 2020 被调整到同日旧合约 2010，消除同一时点新/旧合约的拼接跳空。
        self.assertAlmostEqual(calendar[1]["close"], 2010.0)
        # 后续新合约按同一 factor 调整，保留真实 2020 -> 2030 的市场收益。
        self.assertAlmostEqual(calendar[2]["close"], 2030.0 * 2010.0 / 2020.0)
        self.assertAlmostEqual(
            calendar[2]["close"] / calendar[1]["close"] - 1,
            2030.0 / 2020.0 - 1,
        )

    def test_contract_csv_roll_adjusted_bridge_marks_metadata(self) -> None:
        from goratio.contracts import contract_csv_to_raw_market_data

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "combined_roll.csv"
            path.write_text(
                "date,instrument,symbol,contract_month,close,volume,open_interest\n"
                "2024-01-02,gold,GC,2024-02,2000,100,50\n"
                "2024-01-03,gold,GC,2024-02,2010,80,40\n"
                "2024-01-03,gold,GC,2024-04,2020,200,300\n"
                "2024-01-02,oil,CL,2024-03,75,1000,500\n"
                "2024-01-03,oil,CL,2024-03,80,900,400\n"
                "2024-01-03,oil,CL,2024-05,85,1500,1000\n",
                encoding="utf-8",
            )

            raw = contract_csv_to_raw_market_data(path, roll_adjusted=True)

        self.assertEqual(raw.source.source_id, "contract_csv_roll_adjusted")
        self.assertIn("换月无跳空", raw.source.price_basis)

    def test_summarize_roll_costs_reports_gap_statistics(self) -> None:
        from goratio.contracts import summarize_roll_costs

        records = [
            ContractRecord(
                date=date(2024, 1, 2), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2000.0,
                volume=100, open_interest=50,
            ),
            ContractRecord(
                date=date(2024, 1, 3), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2010.0,
                volume=80, open_interest=40,
            ),
            ContractRecord(
                date=date(2024, 1, 3), instrument="gold", symbol="GC",
                contract_month="2024-04", close=2020.0,
                volume=200, open_interest=300,
                open=2015.0, settle=2018.0,
            ),
        ]

        summary = summarize_roll_costs(records)

        self.assertEqual(summary["roll_event_count"], 1)
        self.assertEqual(summary["measurable_roll_gap_count"], 1)
        self.assertAlmostEqual(summary["mean_abs_roll_gap_bps"], (2020 / 2010 - 1) * 10000)


    def test_roll_aware_contract_return_includes_roll(self) -> None:
        from goratio.contracts import roll_aware_contract_return

        records = [
            ContractRecord(
                date=date(2024, 1, 2), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2000.0,
                volume=100, open_interest=50,
            ),
            ContractRecord(
                date=date(2024, 1, 3), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2010.0,
                volume=80, open_interest=40,
            ),
            ContractRecord(
                date=date(2024, 1, 3), instrument="gold", symbol="GC",
                contract_month="2024-04", close=2020.0,
                volume=200, open_interest=300,
                open=2015.0, settle=2018.0,
            ),
            ContractRecord(
                date=date(2024, 1, 4), instrument="gold", symbol="GC",
                contract_month="2024-04", close=2030.0,
                volume=250, open_interest=400,
            ),
        ]

        ret = roll_aware_contract_return(
            records,
            instrument="gold",
            entry_date=date(2024, 1, 2),
            exit_date=date(2024, 1, 4),
        )

        self.assertAlmostEqual(
            ret,
            (2010 / 2000) * (2030 / 2020) - 1,
        )


    def test_contract_episode_return_summary_uses_roll_aware_return(self) -> None:
        from goratio.contracts import contract_episode_return_summary
        from goratio.episodes import Episode

        records = [
            ContractRecord(
                date=date(2024, 1, 2), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2000.0,
                volume=100, open_interest=50,
            ),
            ContractRecord(
                date=date(2024, 1, 3), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2010.0,
                volume=80, open_interest=40,
            ),
            ContractRecord(
                date=date(2024, 1, 3), instrument="gold", symbol="GC",
                contract_month="2024-04", close=2020.0,
                volume=200, open_interest=300,
                open=2015.0, settle=2018.0,
            ),
            ContractRecord(
                date=date(2024, 1, 4), instrument="gold", symbol="GC",
                contract_month="2024-04", close=2030.0,
                volume=250, open_interest=400,
            ),
        ]
        episode = Episode(
            date=date(2024, 1, 2),
            outcome_date=date(2024, 1, 4),
            forward_return=2030.0 / 2020.0 - 1,
            percentile=0.1,
            history_count=300,
            low_state_days=3,
        )

        summary = contract_episode_return_summary(records, [episode])

        self.assertEqual(summary["episode_count"], 1)
        self.assertEqual(summary["valid_roll_aware_count"], 1)
        self.assertAlmostEqual(
            summary["rows"][0]["roll_aware_return"],
            (2010 / 2000) * (2030 / 2020) - 1,
        )
        self.assertIsNotNone(summary["mean_absolute_difference"])
        self.assertGreaterEqual(summary["valid_t1_open_gap_count"], 1)


    def test_t1_open_settle_gap_uses_optional_fields(self) -> None:
        from goratio.contracts import t1_open_settle_gap

        records = [
            ContractRecord(
                date=date(2024, 1, 2), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2000.0,
                open=2010.0, settle=2005.0,
            ),
            ContractRecord(
                date=date(2024, 1, 3), instrument="gold", symbol="GC",
                contract_month="2024-02", close=2020.0,
                open=2025.0, settle=2018.0,
            ),
        ]

        gap = t1_open_settle_gap(
            records,
            instrument="gold",
            signal_date=date(2024, 1, 2),
        )

        self.assertIsNotNone(gap)
        self.assertEqual(gap["next_date"], "2024-01-03")
        self.assertAlmostEqual(gap["open_gap"], 2025.0 / 2000.0 - 1)
        self.assertAlmostEqual(gap["settle_gap"], 2018.0 / 2000.0 - 1)


if __name__ == "__main__":
    unittest.main()