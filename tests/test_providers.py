import json
import unittest
from unittest.mock import patch

from goratio.providers import (
    HTTPClientError,
    ProviderError,
    SinaProvider,
    UrllibHTTPClient,
    YahooProvider,
)


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


class FakeURLResponse:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.read_limit = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, limit: int) -> bytes:
        self.read_limit = limit
        return self.payload[:limit]


class ProviderTests(unittest.TestCase):
    def test_http_client_rejects_response_larger_than_configured_limit(self) -> None:
        response = FakeURLResponse(b"abcde")

        with patch("goratio.providers.MAX_RESPONSE_BYTES", 4), patch(
            "goratio.providers.urlopen", return_value=response
        ):
            with self.assertRaisesRegex(HTTPClientError, "响应超过.*字节"):
                UrllibHTTPClient().get("https://example.test/data", 1)

        self.assertEqual(response.read_limit, 5)

    def test_http_client_wraps_invalid_utf8_response(self) -> None:
        response = FakeURLResponse(b"\xff")

        with patch("goratio.providers.urlopen", return_value=response):
            with self.assertRaisesRegex(HTTPClientError, "UTF-8"):
                UrllibHTTPClient().get("https://example.test/data", 1)

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
