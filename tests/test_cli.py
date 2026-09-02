import io
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from goratio.cache import CacheStore, DataLoader
from goratio.cli import main
from goratio.providers import RawMarketData, SINA_METADATA


class FixedProvider:
    metadata = SINA_METADATA

    def fetch(self, *, timeout: float = 10) -> RawMarketData:
        return RawMarketData(
            source=self.metadata,
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


class CLITests(unittest.TestCase):
    def make_loader(self, root: Path) -> DataLoader:
        return DataLoader(
            cache=CacheStore(root),
            providers={"cn_public": FixedProvider()},
        )

    def test_now_json_exposes_prices_coverage_and_no_evidence_conclusion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            errors = io.StringIO()
            exit_code = main(
                ["now", "--source", "cn_public", "--period", "5y", "--json"],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=errors,
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(payload["ratio"]["ratio"], 23.75)
        self.assertEqual(payload["evidence_status"]["overall"], "not_evaluated")

    def test_analyze_short_history_returns_insufficient_not_directional_language(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            exit_code = main(
                ["analyze", "--source", "cn_public", "--json"],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(
            all(
                value == "insufficient_data"
                for value in payload["evidence_status"].values()
            )
        )
        self.assertNotIn("建议买入", output.getvalue())
        self.assertNotIn("建议卖出", output.getvalue())

    def test_update_imports_user_csv_into_selected_source_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "owned.csv"
            csv_path.write_text(
                "date,gold_close,oil_close\n"
                "2023-01-02,1800,75\n"
                "2024-01-02,1900,80\n",
                encoding="utf-8",
            )
            loader = self.make_loader(root / "cache")
            output = io.StringIO()

            exit_code = main(
                [
                    "update",
                    "--source",
                    "cn_public",
                    "--import-csv",
                    str(csv_path),
                    "--json",
                ],
                loader=loader,
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )
            cached = loader.cache.load("cn_public")

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "cache_updated")
        self.assertEqual(payload["source"]["provenance"], "user_csv")
        self.assertEqual(cached.provenance, "user_csv")


if __name__ == "__main__":
    unittest.main()
