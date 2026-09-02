import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from goratio.cache import CacheStore, DataLoader, import_standard_csv
from goratio.providers import ProviderError, RawMarketData, SINA_METADATA


def sample_raw(retrieved_at: datetime) -> RawMarketData:
    return RawMarketData(
        source=SINA_METADATA,
        gold_records=({"date": "2024-01-02", "close": "2040"},),
        oil_records=({"date": "2024-01-02", "close": "80"},),
        retrieved_at=retrieved_at,
    )


class FailingProvider:
    metadata = SINA_METADATA

    def fetch(self, *, timeout: float = 10) -> RawMarketData:
        raise ProviderError("模拟在线超时")


class CacheTests(unittest.TestCase):
    def test_round_trip_marks_old_cache_stale_and_keeps_provenance(self) -> None:
        now = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
        old = now - timedelta(hours=73)
        with tempfile.TemporaryDirectory() as directory:
            store = CacheStore(Path(directory), clock=lambda: now)

            store.write(sample_raw(old), provenance="online")
            cached = store.load("cn_public")

        self.assertEqual(cached.raw.gold_records[0]["close"], "2040")
        self.assertEqual(cached.provenance, "online")
        self.assertTrue(cached.stale)
        self.assertAlmostEqual(cached.age_hours, 73.0)

    def test_loader_falls_back_to_cache_and_exposes_online_error(self) -> None:
        now = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            store = CacheStore(Path(directory), clock=lambda: now)
            store.write(sample_raw(now - timedelta(hours=1)))
            loader = DataLoader(
                cache=store,
                providers={"cn_public": FailingProvider()},
            )

            loaded = loader.load("cn_public", timeout=0.1)

        self.assertEqual(loaded.provenance, "cache")
        self.assertIn("模拟在线超时", loaded.warnings[0])
        self.assertEqual(loaded.raw.oil_records[0]["close"], "80")

    def test_standard_csv_is_imported_as_user_owned_cache_input(self) -> None:
        csv_text = (
            "date,gold_close,oil_close\n"
            "2024-01-02,2040.5,72.25\n"
            "2024-01-03,,73.0\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "owned.csv"
            path.write_text(csv_text, encoding="utf-8")

            raw = import_standard_csv(path, SINA_METADATA)

        self.assertEqual(raw.gold_records[1]["close"], "")
        self.assertEqual(raw.oil_records[0]["close"], "72.25")


if __name__ == "__main__":
    unittest.main()
