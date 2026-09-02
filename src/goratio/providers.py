"""内置价格数据来源及其静态注册表。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Mapping, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    """价格来源不可用或响应无效。"""


class HTTPClientError(RuntimeError):
    pass


class UrllibHTTPClient:
    """只暴露本项目需要的有界文本 GET。"""

    def get(self, url: str, timeout: float) -> str:
        request = Request(
            url,
            headers={
                "Accept": "application/json,text/plain,*/*",
                "User-Agent": "goratio/0.1 (+https://github.com/XucroYuri/goratio)",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except HTTPError as exc:
            raise HTTPClientError(f"HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise HTTPClientError(str(exc)) from exc


@dataclass(frozen=True)
class SourceMetadata:
    source_id: str
    name: str
    price_basis: str
    instruments: Mapping[str, Mapping[str, str]]


@dataclass(frozen=True)
class RawMarketData:
    source: SourceMetadata
    gold_records: Tuple[Mapping[str, object], ...]
    oil_records: Tuple[Mapping[str, object], ...]
    retrieved_at: datetime


class PriceProvider(ABC):
    """一期内置数据来源的静态抽象。"""

    @property
    @abstractmethod
    def metadata(self) -> SourceMetadata:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, *, timeout: float = 10) -> RawMarketData:
        raise NotImplementedError


SINA_METADATA = SourceMetadata(
    source_id="cn_public",
    name="新浪财经全球期货日线",
    price_basis="服务商拼接连续期货日收盘价（非交易所结算价）",
    instruments={
        "gold": {
            "symbol": "GC",
            "contract": "COMEX 黄金连续期货",
            "currency": "USD",
            "unit": "troy_ounce",
        },
        "oil": {
            "symbol": "CL",
            "contract": "NYMEX WTI 原油连续期货",
            "currency": "USD",
            "unit": "barrel",
        },
    },
)

YAHOO_METADATA = SourceMetadata(
    source_id="yahoo_futures",
    name="Yahoo Finance Chart API",
    price_basis="服务商连续近月期货日收盘价（非交易所结算价）",
    instruments={
        "gold": {
            "symbol": "GC=F",
            "contract": "COMEX 黄金连续近月期货",
            "currency": "USD",
            "unit": "troy_ounce",
        },
        "oil": {
            "symbol": "CL=F",
            "contract": "NYMEX WTI 原油连续近月期货",
            "currency": "USD",
            "unit": "barrel",
        },
    },
)


class SinaProvider(PriceProvider):
    endpoint = (
        "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
        "var%20_{symbol}=/GlobalFuturesService.getGlobalFuturesDailyKLine"
        "?symbol={symbol}"
    )

    def __init__(self, *, client=None) -> None:
        self.client = client or UrllibHTTPClient()

    @property
    def metadata(self) -> SourceMetadata:
        return SINA_METADATA

    def _fetch_symbol(self, symbol: str, timeout: float):
        url = self.endpoint.format(symbol=symbol)
        try:
            payload = self.client.get(url, timeout)
            marker = payload.find("=(")
            end = payload.rfind(");")
            if marker < 0 or end <= marker:
                raise ValueError("JSONP 外壳缺失")
            rows = json.loads(payload[marker + 2 : end])
            if not isinstance(rows, list) or not rows:
                raise ValueError("返回空数据")
            return tuple(
                {"date": row.get("date"), "close": row.get("close")}
                for row in rows
                if isinstance(row, dict)
            )
        except (HTTPClientError, json.JSONDecodeError, ValueError) as exc:
            raise ProviderError(
                f"国内公开源 {symbol} 获取失败：{exc}；请稍后重试或使用本地缓存"
            ) from exc

    def fetch(self, *, timeout: float = 10) -> RawMarketData:
        return RawMarketData(
            source=self.metadata,
            gold_records=self._fetch_symbol("GC", timeout),
            oil_records=self._fetch_symbol("CL", timeout),
            retrieved_at=datetime.now(timezone.utc),
        )


class YahooProvider(PriceProvider):
    endpoint = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def __init__(self, *, client=None) -> None:
        self.client = client or UrllibHTTPClient()

    @property
    def metadata(self) -> SourceMetadata:
        return YAHOO_METADATA

    def _fetch_symbol(self, symbol: str, timeout: float):
        query = urlencode(
            {
                "range": "max",
                "interval": "1d",
                "events": "history",
                "includeAdjustedClose": "true",
            }
        )
        url = f"{self.endpoint.format(symbol=urlencode_symbol(symbol))}?{query}"
        try:
            payload = json.loads(self.client.get(url, timeout))
            chart = payload["chart"]
            if chart.get("error"):
                raise ValueError(str(chart["error"]))
            result = chart.get("result")
            if not result:
                raise ValueError("返回空数据")
            timestamps = result[0]["timestamp"]
            closes = result[0]["indicators"]["quote"][0]["close"]
            if len(timestamps) != len(closes):
                raise ValueError("日期与价格长度不一致")
            return tuple(
                {
                    "date": datetime.fromtimestamp(ts, timezone.utc)
                    .date()
                    .isoformat(),
                    "close": close,
                }
                for ts, close in zip(timestamps, closes)
            )
        except (
            HTTPClientError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ProviderError(
                f"Yahoo {symbol} 获取失败：{exc}。请检查海外网络与代理配置，或稍后重试；程序将尝试本地缓存"
            ) from exc

    def fetch(self, *, timeout: float = 10) -> RawMarketData:
        return RawMarketData(
            source=self.metadata,
            gold_records=self._fetch_symbol("GC=F", timeout),
            oil_records=self._fetch_symbol("CL=F", timeout),
            retrieved_at=datetime.now(timezone.utc),
        )


def urlencode_symbol(symbol: str) -> str:
    """只转义 Chart API 路径中的期货等号。"""

    return symbol.replace("=", "%3D")


PROVIDERS = {
    "cn_public": SinaProvider,
    "yahoo_futures": YahooProvider,
}


def create_provider(source_id: str) -> PriceProvider:
    try:
        provider_class = PROVIDERS[source_id]
    except KeyError as exc:
        raise ValueError("source 必须是 cn_public 或 yahoo_futures") from exc
    return provider_class()
