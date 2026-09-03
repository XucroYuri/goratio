import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from pathlib import Path

from goratio.cache import CacheStore, DataLoader
from goratio.cli import build_parser, main
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

    def test_version_uses_release_candidate_package_version(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            build_parser().parse_args(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(output.getvalue(), "goratio 0.1.0rc1\n")

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


    def test_plugin_list_json_lists_whitelist_without_loader(self) -> None:
        output = io.StringIO()
        exit_code = main(
            ["plugin", "list", "--json"],
            stdout=output,
            stderr=io.StringIO(),
        )
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["api_version"], "goratio-plugin-v1")
        self.assertGreater(payload["count"], 0)
        for plugin in payload["plugins"]:
            self.assertIn("plugin_id", plugin)
            self.assertIn("read_only", plugin)

    def test_skill_render_contains_read_only_and_china_guidance(self) -> None:
        output = io.StringIO()
        exit_code = main(
            ["skill", "render"],
            stdout=output,
            stderr=io.StringIO(),
        )
        rendered = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("只读研究代理", rendered)
        self.assertIn("中国大陆用户", rendered)
        self.assertIn("不构成投资建议", rendered)

    def test_episode_command_returns_diagnostic_even_on_short_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            exit_code = main(
                ["episode", "--source", "cn_public", "--period", "5y", "--json"],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "goratio-episode-v1")
        self.assertEqual(payload["episode_study"]["episode_count"], 0)
        self.assertEqual(payload["episode_study"]["daily_low_state_event_count"], 0)

    def test_tradability_command_reports_missing_execution_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            exit_code = main(
                ["tradability", "--source", "cn_public", "--period", "5y", "--json"],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "goratio-tradability-v1")
        self.assertEqual(payload["contracts"]["gold"]["contract_multiplier"], 100)
        self.assertEqual(payload["contracts"]["oil"]["contract_multiplier"], 1000)
        self.assertIn("no_roll_calendar", payload["risk_flags"])
        self.assertIn("不构成投资建议", payload["disclaimer"])

    def test_factor_status_returns_v2_spec_and_unavailable_on_short_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            exit_code = main(
                ["factor", "status", "--source", "cn_public", "--period", "5y", "--json"],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "goratio-factor-v1")
        self.assertEqual(payload["protocol"]["id"], "goratio-2a-v1")
        self.assertFalse(payload["snapshot"]["available"])
        self.assertEqual(payload["snapshot"]["reason"], "insufficient_history_for_252d_trend")

    def test_backtest_command_returns_empty_diagnostic_on_short_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            exit_code = main(
                ["backtest", "--source", "cn_public", "--period", "5y", "--json"],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["trade_count"], 0)
        self.assertIn("insufficient_trade_count", payload["risk_flags"])
        self.assertIn("不构成投资建议", payload["disclaimer"])

    def test_episode_study_command_returns_three_horizons(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            exit_code = main(
                ["episode-study", "--source", "cn_public", "--period", "5y", "--json"],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(set(payload["horizons"]), {"63", "126", "252"})
        self.assertTrue(
            all(
                value["evidence_status"] == "insufficient_data"
                for value in payload["horizons"].values()
            )
        )

    def test_contracts_inspect_reads_csv_and_detects_roll(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "contracts.csv"
            csv_path.write_text(
                "date,instrument,symbol,contract_month,close,volume,open_interest\n"
                "2024-01-02,gold,GC,2024-02,2000,100,50\n"
                "2024-01-03,gold,GC,2024-02,2010,80,40\n"
                "2024-01-03,gold,GC,2024-04,2020,200,300\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            exit_code = main(
                ["contracts", "inspect", "--csv", str(csv_path), "--json"],
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["record_count"], 3)
        self.assertEqual(payload["roll_event_count"], 1)
        self.assertEqual(
            payload["roll_events"][0]["new_contract"], "2024-04"
        )

    def test_stress_command_returns_no_events_on_positive_only_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            exit_code = main(
                ["stress", "--source", "cn_public", "--period", "5y", "--json"],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["non_positive_event_count"], 0)
        self.assertEqual(payload["events"], [])


    def test_evidence_command_returns_three_horizons(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            exit_code = main(
                ["evidence", "--source", "cn_public", "--period", "5y", "--json"],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["protocol"], "goratio-2a-v1")
        self.assertEqual(set(payload["horizons"]), {"63", "126", "252"})
        self.assertTrue(
            all(
                value["evidence_status"] == "insufficient_data"
                for value in payload["horizons"].values()
            )
        )


    def test_web_export_writes_readonly_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "dashboard.html"
            errors = io.StringIO()
            exit_code = main(
                [
                    "web", "export", "--source", "cn_public", "--period", "5y",
                    "--output", str(output_path),
                ],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=io.StringIO(),
                stderr=errors,
            )
            rendered = output_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(errors.getvalue(), "")
        self.assertIn("只读研究工作台", rendered)
        self.assertIn("不构成投资建议", rendered)

    def test_contracts_backtest_runs_from_contract_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "contracts.csv"
            csv_path.write_text(
                "date,instrument,symbol,contract_month,close,volume,open_interest\n"
                "2024-01-02,gold,GC,2024-02,2000,100,50\n"
                "2024-01-03,gold,GC,2024-02,2010,80,40\n"
                "2024-01-02,oil,CL,2024-03,75,1000,500\n"
                "2024-01-03,oil,CL,2024-03,80,900,400\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            exit_code = main(
                [
                    "contracts", "backtest", "--csv", str(csv_path),
                    "--horizon", "63", "--json",
                ],
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["trade_count"], 0)
        self.assertEqual(payload["source_id"], "contract_csv")
        self.assertIn("不构成投资建议", payload["disclaimer"])

    def test_formal_command_returns_v2_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            exit_code = main(
                ["formal", "--source", "cn_public", "--period", "5y", "--json"],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["protocol"], "goratio-2a-v1")
        self.assertEqual(payload["overall_status"], "insufficient_data")

    def test_contracts_portfolio_runs_from_contract_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "contracts.csv"
            csv_path.write_text(
                "date,instrument,symbol,contract_month,close,volume,open_interest\n"
                "2024-01-02,gold,GC,2024-02,2000,100,50\n"
                "2024-01-03,gold,GC,2024-02,2010,80,40\n"
                "2024-01-02,oil,CL,2024-03,75,1000,500\n"
                "2024-01-03,oil,CL,2024-03,80,900,400\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            exit_code = main(
                [
                    "contracts", "portfolio", "--csv", str(csv_path),
                    "--horizon", "63", "--json",
                ],
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["simulation"]["episode_count"], 0)

    def test_contracts_net_backtest_runs_from_contract_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "contracts.csv"
            csv_path.write_text(
                "date,instrument,symbol,contract_month,close,volume,open_interest\n"
                "2024-01-02,gold,GC,2024-02,2000,100,50\n"
                "2024-01-03,gold,GC,2024-02,2010,80,40\n"
                "2024-01-02,oil,CL,2024-03,75,1000,500\n"
                "2024-01-03,oil,CL,2024-03,80,900,400\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            exit_code = main(
                [
                    "contracts", "net-backtest", "--csv", str(csv_path),
                    "--horizon", "63", "--json",
                ],
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["execution"], "open")
        self.assertEqual(payload["episode_count"], 0)

    def test_contracts_roll_cost_runs_from_contract_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "contracts.csv"
            csv_path.write_text(
                "date,instrument,symbol,contract_month,close,volume,open_interest\n"
                "2024-01-02,gold,GC,2024-02,2000,100,50\n"
                "2024-01-03,gold,GC,2024-02,2010,80,40\n"
                "2024-01-03,gold,GC,2024-04,2020,200,300\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            exit_code = main(
                ["contracts", "roll-cost", "--csv", str(csv_path), "--json"],
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["roll_event_count"], 1)

    def test_overview_command_returns_v2_overview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            exit_code = main(
                ["overview", "--source", "cn_public", "--period", "5y", "--json"],
                loader=self.make_loader(Path(directory)),
                today=lambda: date(2024, 1, 4),
                stdout=output,
                stderr=io.StringIO(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["protocol"], "goratio-2a-v1")
        self.assertEqual(payload["overview"]["overall_status"], "insufficient_data")

    def test_governance_command_returns_freeze_checklist(self) -> None:
        output = io.StringIO()
        exit_code = main(
            ["governance", "--json"],
            stdout=output,
            stderr=io.StringIO(),
        )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["protocol_id"], "goratio-2a-v1")
        self.assertFalse(payload["external_review"])

if __name__ == "__main__":
    unittest.main()