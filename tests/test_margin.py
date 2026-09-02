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


if __name__ == "__main__":
    unittest.main()
