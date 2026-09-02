import json
import unittest
from datetime import date, timedelta

from goratio.data import AlignedPoint
from goratio.episodes import (
    build_forward_episodes,
    collapse_low_state_episodes,
    split_episode_counts,
    summarize_episode_research,
)
from goratio.research import build_forward_events


def _point(day: date, ratio: float, gold: float = 1000.0) -> AlignedPoint:
    return AlignedPoint(
        date=day,
        gold_close=gold,
        oil_close=gold / ratio,
        ratio=ratio,
    )


def _sample_points():
    start = date(2020, 1, 1)
    points = []
    blocks = [(250, 285), (500, 535), (750, 785)]
    for index in range(800):
        ratio = 10 if any(a <= index < b for a, b in blocks) else 30
        points.append(
            _point(start + timedelta(days=index), ratio, gold=1000 + index)
        )
    return tuple(points)


class EpisodeConstructionTests(unittest.TestCase):
    def test_low_state_runs_are_compressed_into_episodes(self) -> None:
        history = _sample_points()
        selected = history[200:]
        horizon = 10

        daily_events = build_forward_events(history, selected, horizon=horizon)
        episodes = collapse_low_state_episodes(daily_events)

        daily_low_count = sum(1 for event in daily_events if event.low_state)
        self.assertGreater(daily_low_count, 100)
        self.assertEqual(len(episodes), 3)
        self.assertGreater(daily_low_count / len(episodes), 30)

    def test_build_forward_episodes_returns_serializable_summary(self) -> None:
        history = _sample_points()
        episodes = build_forward_episodes(
            history, history[200:], horizon=10
        )

        summary = summarize_episode_research(
            history, history[200:], horizon=10
        )

        self.assertEqual(len(episodes), 3)
        self.assertEqual(summary["episode_count"], 3)
        self.assertEqual(len(summary["episodes"]), 3)
        self.assertIsNotNone(summary["episode_returns"]["median"])
        self.assertIsNotNone(summary["episode_returns"]["mean"])
        self.assertIn("method", summary)
        # Episode 输出必须可直接进入严格 JSON 契约。
        json.dumps(summary, ensure_ascii=False, allow_nan=False)

    def test_episode_split_purges_boundary_labels(self) -> None:
        history = _sample_points()
        episodes = build_forward_episodes(
            history, history[200:], horizon=30
        )
        # Place split after the first low block's entry but before its outcome.
        split = history[260].date

        counts = split_episode_counts(episodes, split_date=split, horizon=30)

        self.assertEqual(counts["episode_count"], 3)
        self.assertEqual(counts["purged_boundary_episodes"], 1)
        self.assertEqual(counts["out_of_sample_episodes"], 2)


if __name__ == "__main__":
    unittest.main()
