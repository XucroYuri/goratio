"""本地缓存、用户 CSV 导入和在线降级。"""

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Mapping, Optional, Tuple

from .providers import (
    PriceProvider,
    ProviderError,
    RawMarketData,
    SourceMetadata,
    create_provider,
)


CACHE_SCHEMA_VERSION = "goratio-cache-v1"


class CacheError(RuntimeError):
    """缓存缺失、损坏或契约不兼容。"""


class DataUnavailableError(RuntimeError):
    """在线和缓存数据都不可用。"""


@dataclass(frozen=True)
class CachedData:
    raw: RawMarketData
    provenance: str
    saved_at: datetime
    age_hours: float
    stale: bool
    snapshot_sha256: str


@dataclass(frozen=True)
class LoadedData:
    raw: RawMarketData
    provenance: str
    cache_origin: Optional[str]
    cache_age_hours: Optional[float]
    cache_stale: bool
    snapshot_sha256: str
    warnings: Tuple[str, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical_payload(raw: RawMarketData) -> Mapping[str, object]:
    return {
        "source": asdict(raw.source),
        "retrieved_at": _iso_z(raw.retrieved_at),
        "gold_records": [dict(record) for record in raw.gold_records],
        "oil_records": [dict(record) for record in raw.oil_records],
    }


def raw_data_hash(raw: RawMarketData) -> str:
    encoded = json.dumps(
        _canonical_payload(raw),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CacheStore:
    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] = _utc_now,
        stale_after_hours: float = 72,
    ) -> None:
        self.root = Path(root)
        self.clock = clock
        self.stale_after_hours = stale_after_hours

    def path_for(self, source_id: str) -> Path:
        if source_id not in {"cn_public", "yahoo_futures"}:
            raise CacheError("不支持的缓存来源")
        return self.root / f"{source_id}.json"

    def write(self, raw: RawMarketData, *, provenance: str = "online") -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "saved_at": _iso_z(self.clock()),
            "provenance": provenance,
            "snapshot_sha256": raw_data_hash(raw),
            "data": _canonical_payload(raw),
        }
        target = self.path_for(raw.source.source_id)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(self.root)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        return target

    def load(self, source_id: str) -> CachedData:
        path = self.path_for(source_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["schema_version"] != CACHE_SCHEMA_VERSION:
                raise CacheError("缓存版本不兼容")
            data = payload["data"]
            source = SourceMetadata(**data["source"])
            if source.source_id != source_id:
                raise CacheError("缓存来源与文件名不一致")
            raw = RawMarketData(
                source=source,
                gold_records=tuple(data["gold_records"]),
                oil_records=tuple(data["oil_records"]),
                retrieved_at=_parse_datetime(data["retrieved_at"]),
            )
            expected_hash = payload["snapshot_sha256"]
            if raw_data_hash(raw) != expected_hash:
                raise CacheError("缓存摘要校验失败")
            saved_at = _parse_datetime(payload["saved_at"])
            age = max(
                0.0,
                (self.clock().astimezone(timezone.utc) - raw.retrieved_at).total_seconds()
                / 3600,
            )
            return CachedData(
                raw=raw,
                provenance=payload["provenance"],
                saved_at=saved_at,
                age_hours=age,
                stale=age > self.stale_after_hours,
                snapshot_sha256=expected_hash,
            )
        except FileNotFoundError as exc:
            raise CacheError(f"未找到 {source_id} 本地缓存") from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CacheError(f"{source_id} 缓存损坏：{exc}") from exc


def default_cache_store() -> CacheStore:
    configured = os.environ.get("GORATIO_CACHE_DIR")
    root = Path(configured).expanduser() if configured else Path.home() / ".goratio" / "cache"
    return CacheStore(root)


class DataLoader:
    def __init__(
        self,
        *,
        cache: Optional[CacheStore] = None,
        providers: Optional[Mapping[str, PriceProvider]] = None,
    ) -> None:
        self.cache = cache or default_cache_store()
        self.providers = providers

    def _provider_for(self, source_id: str) -> PriceProvider:
        if self.providers is not None:
            try:
                return self.providers[source_id]
            except KeyError as exc:
                raise ValueError("source 必须是 cn_public 或 yahoo_futures") from exc
        return create_provider(source_id)

    def provider_metadata(self, source_id: str) -> SourceMetadata:
        return self._provider_for(source_id).metadata

    def load(self, source_id: str, *, timeout: float = 10) -> LoadedData:
        provider = self._provider_for(source_id)
        try:
            raw = provider.fetch(timeout=timeout)
            self.cache.write(raw, provenance="online")
            return LoadedData(
                raw=raw,
                provenance="online",
                cache_origin=None,
                cache_age_hours=0.0,
                cache_stale=False,
                snapshot_sha256=raw_data_hash(raw),
                warnings=(),
            )
        except ProviderError as online_error:
            try:
                cached = self.cache.load(source_id)
            except CacheError as cache_error:
                raise DataUnavailableError(
                    f"{online_error}；{cache_error}。可用 update --import-csv 导入自有 CSV"
                ) from cache_error
            warnings = [f"在线来源不可用，已降级到本地缓存：{online_error}"]
            if cached.stale:
                warnings.append(
                    f"缓存已陈旧（{cached.age_hours:.1f} 小时），请核对最新交易日"
                )
            return LoadedData(
                raw=cached.raw,
                provenance="cache",
                cache_origin=cached.provenance,
                cache_age_hours=cached.age_hours,
                cache_stale=cached.stale,
                snapshot_sha256=cached.snapshot_sha256,
                warnings=tuple(warnings),
            )

    def update(self, source_id: str, *, timeout: float = 10) -> LoadedData:
        provider = self._provider_for(source_id)
        raw = provider.fetch(timeout=timeout)
        self.cache.write(raw, provenance="online")
        return LoadedData(
            raw=raw,
            provenance="online",
            cache_origin=None,
            cache_age_hours=0.0,
            cache_stale=False,
            snapshot_sha256=raw_data_hash(raw),
            warnings=(),
        )


def import_standard_csv(
    path: Path,
    source: SourceMetadata,
    *,
    retrieved_at: Optional[datetime] = None,
) -> RawMarketData:
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"date", "gold_close", "oil_close"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("CSV 必须包含 date,gold_close,oil_close")
            rows = tuple(reader)
    except OSError as exc:
        raise ValueError(f"无法读取 CSV：{exc}") from exc
    if not rows:
        raise ValueError("CSV 不包含数据行")
    return RawMarketData(
        source=source,
        gold_records=tuple(
            {"date": row["date"], "close": row["gold_close"]} for row in rows
        ),
        oil_records=tuple(
            {"date": row["date"], "close": row["oil_close"]} for row in rows
        ),
        retrieved_at=retrieved_at or _utc_now(),
    )
