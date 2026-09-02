import unittest

from goratio.margin import one_gc_one_cl_margin_report, position_margin_estimate


class MarginTests(unittest.TestCase):
    def test_position_margin_estimate_uses_contract_multipliers(self) -> None:
        result = position_margin_estimate(2000, 80, gc_lots=1, cl_lots=1)

        self.assertEqual(result["gc_notional"], 2000 * 100)
        self.assertEqual(result["cl_notional"], 80 * 1000)
        self.assertAlmostEqual(
            result["margin_estimate"],
            2000 * 100 * 0.05 + 80 * 1000 * 0.10,
        )
        self.assertIn("不构成仓位建议", result["note"])

    def test_one_gc_one_cl_report(self) -> None:
        report = one_gc_one_cl_margin_report(2000, 80)

        self.assertIn("one_gc_only", report)
        self.assertIn("one_gc_one_cl", report)




from datetime import date
from goratio.contracts import ContractRecord
from goratio.margin import position_pnl_estimate


class PositionPnlTests(unittest.TestCase):
    def test_position_pnl_estimate_uses_roll_aware_return(self) -> None:
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
            ),
            ContractRecord(
                date=date(2024, 1, 4), instrument="gold", symbol="GC",
                contract_month="2024-04", close=2030.0,
                volume=250, open_interest=400,
            ),
        ]

        result = position_pnl_estimate(
            records,
            instrument="gold",
            entry_date=date(2024, 1, 2),
            exit_date=date(2024, 1, 4),
            direction=1,
            lots=1,
        )

        expected_return = (2010 / 2000) * (2030 / 2020) - 1
        self.assertAlmostEqual(result["roll_aware_return"], expected_return)
        self.assertAlmostEqual(result["notional"], 2000 * 100)
        self.assertAlmostEqual(
            result["pnl_estimate"], 2000 * 100 * expected_return
        )
        self.assertGreater(result["margin_estimate"], 0)


    def test_run_position_simulation_batch(self) -> None:
        from datetime import timedelta
        from goratio.episodes import Episode
        from goratio.margin import run_position_simulation

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
            forward_return=0.0,
            percentile=0.1,
            history_count=300,
            low_state_days=3,
        )

        sim = run_position_simulation(records, [episode], lots=1)

        self.assertEqual(sim["episode_count"], 1)
        self.assertEqual(sim["valid_pnl_count"], 1)
        self.assertGreater(sim["mean_pnl_estimate"], 0)


if __name__ == "__main__":
    unittest.main()