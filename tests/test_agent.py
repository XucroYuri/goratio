import io
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from goratio.agent import (
    TOOLS,
    invoke_tool,
    mcp_handle_message,
    render_skill,
    serve,
)
from goratio.cache import CacheStore, DataLoader
from goratio.providers import ProviderError, RawMarketData, SINA_METADATA


def sample_raw() -> RawMarketData:
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


class RejectingProvider:
    metadata = SINA_METADATA

    def fetch(self, *, timeout: float = 10):
        raise ProviderError("MCP 不得调用在线数据源")


class AgentTests(unittest.TestCase):
    def make_loader(self, root: Path) -> DataLoader:
        store = CacheStore(root)
        store.write(sample_raw())
        return DataLoader(
            cache=store,
            providers={"cn_public": RejectingProvider()},
        )

    def test_mcp_initialize_and_tool_list_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loader = self.make_loader(Path(directory))

            initialized = mcp_handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"},
                    },
                },
                loader,
            )
            tools = mcp_handle_message(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                loader,
            )

        self.assertEqual(
            initialized["result"]["serverInfo"]["name"], "goratio-readonly"
        )
        self.assertEqual(tools["result"]["tools"][0]["name"], TOOLS[0]["name"])
        self.assertTrue(
            all(
                tool["name"] in {"get_data_quality", "get_ratio_snapshot", "run_research_protocol", "get_risk_flags", "list_protocols"}
                for tool in tools["result"]["tools"]
            )
        )

    def test_cache_based_snapshot_does_not_trigger_online_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loader = self.make_loader(Path(directory))

            response = mcp_handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {
                        "name": "get_ratio_snapshot",
                        "arguments": {"source": "cn_public", "period": "5y"},
                    },
                },
                loader,
                completed_before=date(2024, 1, 4),
            )

        self.assertFalse(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["as_of"], "2024-01-02")
        self.assertEqual(payload["ratio"]["ratio"], 23.75)

    def test_protocol_list_tool_is_available_without_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CacheStore(Path(directory))
            loader = DataLoader(cache=store, providers={"cn_public": RejectingProvider()})

            response = invoke_tool(loader, "list_protocols")

        content = json.loads(response["content"][0]["text"])
        self.assertEqual(content["protocols"][0]["status"], "frozen")

    def test_missing_cache_returns_tool_error_and_does_not_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loader = DataLoader(
                cache=CacheStore(Path(directory)),
                providers={"cn_public": RejectingProvider()},
            )

            response = invoke_tool(
                loader,
                "get_data_quality",
                completed_before=date(2024, 1, 4),
            )

        self.assertTrue(response["isError"])
        self.assertIn("如需在线数据", response["content"][0]["text"])

    def test_skill_contains_read_only_and_disclaimer_rules(self) -> None:
        skill = render_skill()
        self.assertIn("只读研究代理", skill)
        self.assertIn("不提供买入、卖出、仓位或收益承诺", skill)
        self.assertIn("不构成投资建议", skill)
        self.assertIn("数据不足", skill)

    def test_serve_round_trip_stdout_protocol_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loader = self.make_loader(Path(directory))
            stdin = io.StringIO(
                '{"jsonrpc":"2.0","id":1,"method":"ping"}\n'
                '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_protocols","arguments":{}}}\n'
            )
            stdout = io.StringIO()

            serve(loader, stdin=stdin, stdout=stdout)

            lines = [line for line in stdout.getvalue().splitlines() if line]
            self.assertEqual(len(lines), 2)
            ping = json.loads(lines[0])
            called = json.loads(lines[1])
            self.assertEqual(ping["result"], {})
            self.assertFalse(called["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
