import json
import unittest

from goratio.providers import ProviderError, SinaProvider, YahooProvider


class FakeHTTPClient:
    def __init__(self, responses):
        self.responses = responses
        self.timeouts = []

    def get(self, url: str, timeout: float) -> str:
        self.timeouts.append(timeout)
        for marker, response in self.responses.items():
            if marker in url:
                return response
        raise AssertionError(f"unexpected URL: {url}")


class ProviderTests(unittest.TestCase):
    def test_sina_parses_both_continuous_futures_from_jsonp(self) -> None:
        client = FakeHTTPClient(
            {
                "symbol=GC": (
                    "/*redirect guard*/\nvar _GC=(["
                    '{"date":"2024-01-02","close":"2040.50"}'
                    "]);"
                ),
                "symbol=CL": (
                    "var _CL=(["
                    '{"date":"2024-01-02","close":"72.25"}'
                    "]);"
                ),
            }
        )

        result = SinaProvider(client=client).fetch(timeout=2.5)

        self.assertEqual(result.source.source_id, "cn_public")
        self.assertEqual(result.gold_records[0]["date"], "2024-01-02")
        self.assertEqual(result.gold_records[0]["close"], "2040.50")
        self.assertEqual(result.oil_records[0]["close"], "72.25")
        self.assertEqual(client.timeouts, [2.5, 2.5])

    def test_yahoo_parses_utc_dates_and_preserves_missing_values_for_audit(self) -> None:
        response = json.dumps(
            {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1704153600, 1704240000],
                            "indicators": {
                                "quote": [{"close": [2040.5, None]}]
                            },
                        }
                    ],
                    "error": None,
                }
            }
        )
        client = FakeHTTPClient({"GC%3DF": response, "CL%3DF": response})

        result = YahooProvider(client=client).fetch(timeout=3)

        self.assertEqual(result.source.source_id, "yahoo_futures")
        self.assertEqual(
            result.gold_records,
            (
                {"date": "2024-01-02", "close": 2040.5},
                {"date": "2024-01-03", "close": None},
            ),
        )

    def test_yahoo_empty_response_has_network_troubleshooting_message(self) -> None:
        client = FakeHTTPClient({"GC%3DF": '{"chart":{"result":null,"error":null}}'})

        with self.assertRaisesRegex(
            ProviderError, "海外网络.*代理.*稍后重试"
        ):
            YahooProvider(client=client).fetch(timeout=1)


if __name__ == "__main__":
    unittest.main()
