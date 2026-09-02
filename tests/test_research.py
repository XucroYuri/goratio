import unittest
from datetime import date, timedelta
from datetime import datetime, timezone
import math
import random

from goratio.data import AlignedPoint
from goratio.dataset import prepare_market_data
from goratio.providers import RawMarketData, SINA_METADATA
from goratio.research import (
    ForwardEvent,
    _moving_block_sample,
    adf_mean_reversion,
    build_forward_events,
    compare_source_results,
    structural_break_diagnostic,
    summarize_event_records,
    summarize_current,
    run_research,
)


def point(day: date, ratio: float, gold: float = 2000.0) -> AlignedPoint:
    return AlignedPoint(
        date=day,
        gold_close=gold,
        oil_close=gold / ratio,
        ratio=ratio,
    )


class CurrentStatisticsTests(unittest.TestCase):
    def test_current_state_uses_trailing_five_year_median_and_empirical_rank(self) -> None:
        start = date(2023, 1, 1)
        history = tuple(
            point(start + timedelta(days=index), 10.0) for index in range(251)
        ) + (point(start + timedelta(days=251), 20.0),)

        result = summarize_current(history, history)

        self.assertEqual(result["as_of"], "2023-09-09")
        self.assertEqual(result["ratio"], 20.0)
        self.assertEqual(result["rolling_center"], 10.0)
        self.assertEqual(result["deviation"], 1.0)
        self.assertEqual(result["historical_percentile"], 1.0)
        self.assertEqual(result["rolling_observation_count"], 252)


class MeanReversionTests(unittest.TestCase):
    def test_adf_marks_strong_stationary_log_ratio_as_supported(self) -> None:
        generator = random.Random(7)
        level = 0.0
        points = []
        start = date(2020, 1, 1)
        for index in range(600):
            level = 0.45 * level + generator.gauss(0, 0.05)
            ratio = math.exp(3 + level)
            points.append(point(start + timedelta(days=index), ratio))

        result = adf_mean_reversion(points)

        self.assertEqual(result["method"], "ADF(1)_with_intercept")
        self.assertLessEqual(result["t_statistic"], -2.86)
        self.assertEqual(result["status"], "supported")


class StructuralBreakTests(unittest.TestCase):
    def test_moving_block_sample_rejects_non_positive_block_length(self) -> None:
        for block_length in (0, -1):
            with self.subTest(block_length=block_length), self.assertRaisesRegex(
                ValueError, "block_length.*正整数"
            ):
                _moving_block_sample([], block_length, random.Random(7))

    def test_sup_f_flags_a_large_persistent_level_shift(self) -> None:
        start = date(2018, 1, 1)
        points = tuple(
            point(
                start + timedelta(days=index),
                (20.0 if index < 600 else 40.0) + (index % 7) / 100,
            )
            for index in range(1200)
        )

        result = structural_break_diagnostic(points, bootstrap_repetitions=99)

        self.assertEqual(result["method"], "single_mean_shift_sup_f")
        self.assertEqual(result["break_date"], (start + timedelta(days=600)).isoformat())
        self.assertLess(result["bootstrap_p_value"], 0.05)
        self.assertEqual(result["status"], "unstable")


class EventConstructionTests(unittest.TestCase):
    def test_state_uses_only_trailing_values_and_return_uses_exact_future_index(self) -> None:
        start = date(2024, 1, 1)
        points = tuple(
            point(
                start + timedelta(days=index),
                1.0 if index == 251 else 10.0,
                gold=100.0 + index,
            )
            for index in range(260)
        )

        events = build_forward_events(points, points, horizon=2)

        first = events[0]
        self.assertEqual(first.date, start + timedelta(days=251))
        self.assertTrue(first.low_state)
        self.assertAlmostEqual(first.forward_return, 353 / 351 - 1)
        self.assertEqual(first.history_count, 252)

    def test_oos_evidence_uses_fixed_split_and_familywise_interval(self) -> None:
        start = date(2020, 1, 1)
        events = tuple(
            ForwardEvent(
                date=start + timedelta(days=index),
                forward_return=0.2 if index % 2 == 0 else 0.0,
                low_state=index % 2 == 0,
                percentile=0.1 if index % 2 == 0 else 0.8,
                history_count=300,
                outcome_date=start + timedelta(days=index + 1),
            )
            for index in range(400)
        )

        result = summarize_event_records(
            events,
            split_date=start + timedelta(days=280),
            horizon=63,
            evidence_eligible=True,
            bootstrap_repetitions=99,
        )

        self.assertEqual(result["split"]["rule"], "chronological_70_30")
        self.assertEqual(result["out_of_sample"]["conditional"]["sample_count"], 60)
        self.assertAlmostEqual(
            result["out_of_sample"]["difference"]["mean"], 0.1
        )
        self.assertGreater(
            result["out_of_sample"]["difference"]["familywise_ci_98_33"][0],
            0,
        )
        self.assertEqual(result["evidence_status"], "supported")

    def test_chronological_split_purges_labels_that_cross_boundary(self) -> None:
        start = date(2024, 1, 1)
        events = (
            ForwardEvent(start, 0.1, True, 0.1, 300, start + timedelta(days=2)),
            ForwardEvent(
                start + timedelta(days=1),
                0.2,
                True,
                0.1,
                300,
                start + timedelta(days=4),
            ),
            ForwardEvent(
                start + timedelta(days=3),
                0.3,
                True,
                0.1,
                300,
                start + timedelta(days=5),
            ),
        )

        result = summarize_event_records(
            events,
            split_date=start + timedelta(days=3),
            horizon=2,
            evidence_eligible=True,
            bootstrap_repetitions=9,
        )

        self.assertEqual(result["split"]["in_sample_event_observations"], 1)
        self.assertEqual(result["split"]["purged_boundary_events"], 1)
        self.assertEqual(result["split"]["out_of_sample_event_observations"], 1)


class ResearchProtocolTests(unittest.TestCase):
    def test_short_history_forces_every_hypothesis_to_insufficient_data(self) -> None:
        raw = RawMarketData(
            source=SINA_METADATA,
            gold_records=tuple(
                {"date": f"2024-01-{day:02d}", "close": 2000 + day}
                for day in range(1, 21)
            ),
            oil_records=tuple(
                {"date": f"2024-01-{day:02d}", "close": 80 + day / 10}
                for day in range(1, 21)
            ),
            retrieved_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        )
        prepared = prepare_market_data(
            raw,
            period="5y",
            completed_before=date(2024, 2, 1),
            provenance="online",
            cache_stale=False,
        )

        result = run_research(
            prepared,
            event_bootstrap_repetitions=9,
            structural_bootstrap_repetitions=9,
        )

        self.assertEqual(result["protocol_version"], "goratio-1a-v1")
        self.assertEqual(result["trial_count"], 6)
        self.assertTrue(
            all(
                status == "insufficient_data"
                for status in result["evidence_status"].values()
            )
        )
        self.assertIn("insufficient_history", result["risk_flags"])

    def test_cross_source_replication_requires_matching_status_and_direction(self) -> None:
        def result(direction: float):
            return {
                "mean_reversion": {"status": "not_supported"},
                "stability_diagnostic": {"status": "stable"},
                "replication": {"cross_time_status": "supported"},
                "event_study": {
                    "horizons": {
                        str(horizon): {
                            "evidence_status": "not_supported",
                            "out_of_sample": {
                                "difference": {"mean": direction}
                            },
                        }
                        for horizon in (63, 126, 252)
                    }
                },
            }

        matched = compare_source_results(
            result(0.1), result(0.2), "cn_public", "yahoo_futures"
        )
        reversed_result = compare_source_results(
            result(0.1), result(-0.2), "cn_public", "yahoo_futures"
        )

        self.assertEqual(matched["status"], "supported")
        self.assertEqual(reversed_result["status"], "not_supported")


if __name__ == "__main__":
    unittest.main()
