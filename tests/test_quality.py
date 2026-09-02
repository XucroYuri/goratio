import unittest
from datetime import date

from goratio.data import AlignedPoint, AlignedSeries, align_series, select_period, validate_series


class ValidateSeriesTests(unittest.TestCase):
    def test_rejects_invalid_prices_and_conflicting_duplicate_date(self) -> None:
        records = [
            {"date": "2024-01-02", "close": "10"},
            {"date": "2024-01-02", "close": "10"},
            {"date": "2024-01-03", "close": "11"},
            {"date": "2024-01-03", "close": "12"},
            {"date": "2024-01-04", "close": ""},
            {"date": "2024-01-05", "close": "nan"},
            {"date": "2024-01-06", "close": "0"},
            {"date": "not-a-date", "close": "13"},
            {"date": "2024-01-10", "close": "14"},
        ]

        result = validate_series(
            "gold", records, completed_before=date(2024, 1, 10)
        )

        self.assertEqual(
            [(point.date.isoformat(), point.close) for point in result.points],
            [("2024-01-02", 10.0)],
        )
        self.assertEqual(result.audit.input_records, 9)
        self.assertEqual(result.audit.duplicate_identical, 1)
        self.assertEqual(result.audit.duplicate_conflict, 2)
        self.assertEqual(result.audit.missing_close, 1)
        self.assertEqual(result.audit.non_finite, 1)
        self.assertEqual(result.audit.non_positive, 1)
        self.assertEqual(result.audit.invalid_date, 1)
        self.assertEqual(result.audit.future_or_incomplete, 1)

    def test_alignment_keeps_only_same_day_closes_without_forward_fill(self) -> None:
        gold = validate_series(
            "gold",
            [
                {"date": "2024-01-02", "close": "2000"},
                {"date": "2024-01-03", "close": "2020"},
            ],
            completed_before=date(2024, 1, 5),
        )
        oil = validate_series(
            "oil",
            [
                {"date": "2024-01-02", "close": "80"},
                {"date": "2024-01-04", "close": "81"},
            ],
            completed_before=date(2024, 1, 5),
        )

        result = align_series(gold, oil)

        self.assertEqual(len(result.points), 1)
        self.assertEqual(result.points[0].date.isoformat(), "2024-01-02")
        self.assertEqual(result.points[0].ratio, 25.0)
        self.assertEqual(result.gold_unmatched, 1)
        self.assertEqual(result.oil_unmatched, 1)

    def test_extreme_log_return_is_flagged_but_not_removed(self) -> None:
        closes = [100, 101, 102, 103, 104, 500, 505, 510, 515]
        records = [
            {"date": f"2024-01-{index + 1:02d}", "close": close}
            for index, close in enumerate(closes)
        ]

        result = validate_series(
            "oil", records, completed_before=date(2024, 2, 1)
        )

        self.assertEqual(len(result.points), len(closes))
        self.assertEqual(result.audit.outlier_candidates, 1)

    def test_period_uses_calendar_years_and_handles_leap_day(self) -> None:
        aligned = AlignedSeries(
            points=(
                AlignedPoint(date(2021, 2, 27), 1800, 60, 30),
                AlignedPoint(date(2021, 2, 28), 1810, 60, 181 / 6),
                AlignedPoint(date(2024, 2, 29), 2000, 80, 25),
            ),
            gold_unmatched=0,
            oil_unmatched=0,
        )

        result = select_period(aligned, "3y")

        self.assertEqual(
            [point.date.isoformat() for point in result.points],
            ["2021-02-28", "2024-02-29"],
        )


if __name__ == "__main__":
    unittest.main()
