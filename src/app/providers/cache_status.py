"""Provider/model cache status without heavyweight provider instantiation."""
from __future__ import annotations

import json
import os
import sqlite3
import socket
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.jobs.executor import JobHandler
from app.jobs.models import CreateJobRequest, JobStage, ResourceClass
from app.jobs.models import JobRecord
from app.providers.facade import default_provider_facade
from app.runtime_paths import resources_data_root, resources_models_root


CacheStatus = Literal["available", "configured", "missing_path", "not_configured", "unreachable"]
RefreshScope = Literal["providers", "models", "all"]


class ProviderModelCacheEntry(BaseModel):
    id: str
    provider_id: str
    model_id: str = ""
    status: CacheStatus
    source: str
    path: str | None = None
    diagnostics: list[dict[str, str]] = Field(default_factory=list)


class ProviderModelCachePayload(BaseModel):
    status: str
    entries: list[ProviderModelCacheEntry] = Field(default_factory=list)
    diagnostics: list[dict[str, str]] = Field(default_factory=list)


class ProviderModelRefreshRequest(BaseModel):
    scope: RefreshScope = "all"
    reason: str | None = None
    priority: int = 0


class ProviderModelRefreshSnapshot(BaseModel):
    id: str
    scope: RefreshScope
    reason: str | None = None
    status: str
    provider_count: int = 0
    model_count: int = 0
    cache_status: str
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    provider_payload: dict[str, Any] = Field(default_factory=dict)
    cache_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ProviderModelRefreshHistory(BaseModel):
    snapshots: list[ProviderModelRefreshSnapshot] = Field(default_factory=list)


SettingsLoader = Callable[[], dict[str, Any]]
PathExists = Callable[[Path], bool]
UrlReachable = Callable[[str], bool]
ProviderFacadeFactory = Callable[[], Any]
CacheStatusFactory = Callable[[], ProviderModelCachePayload]


def default_provider_model_refresh_db_path() -> Path:
    override = os.environ.get("OMNIX_PROVIDER_MODEL_REFRESH_DB_PATH")
    if override:
        return Path(override)
    return resources_data_root() / "omnix_provider_model_refresh.sqlite"


class SQLiteProviderModelRefreshStore:
    """Durable provider/model discovery refresh history."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_provider_model_refresh_db_path()
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_model_refresh_snapshots (
                    id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_provider_model_refresh_created
                ON provider_model_refresh_snapshots(created_at)
                """
            )

    def record_snapshot(
        self,
        *,
        scope: RefreshScope,
        reason: str | None,
        provider_payload: Any,
        cache_payload: Any,
    ) -> ProviderModelRefreshSnapshot:
        provider_data = _payload_to_dict(provider_payload)
        cache_data = _payload_to_dict(cache_payload)
        provider_count = len(_safe_list(provider_data.get("providers")))
        model_count = len(_safe_list(provider_data.get("models")))
        cache_status = _safe_str(cache_data.get("status")).strip() or "unknown"
        diagnostics = [item for item in _safe_list(cache_data.get("diagnostics")) if isinstance(item, dict)]
        snapshot = ProviderModelRefreshSnapshot(
            id=f"provider-model-refresh:{uuid.uuid4().hex}",
            scope=scope,
            reason=reason,
            status="degraded" if diagnostics or cache_status == "degraded" else "ready",
            provider_count=provider_count,
            model_count=model_count,
            cache_status=cache_status,
            diagnostics=diagnostics,
            provider_payload=provider_data,
            cache_payload=cache_data,
            created_at=_utcnow(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_model_refresh_snapshots (id, scope, status, created_at, snapshot_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    snapshot.scope,
                    snapshot.status,
                    snapshot.created_at,
                    json.dumps(snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
                ),
            )
        return snapshot

    def latest_snapshot(self) -> ProviderModelRefreshSnapshot | None:
        snapshots = self.list_snapshots(limit=1)
        return snapshots[0] if snapshots else None

    def list_snapshots(self, *, limit: int = 20) -> list[ProviderModelRefreshSnapshot]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT snapshot_json FROM provider_model_refresh_snapshots
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [ProviderModelRefreshSnapshot(**_json_loads(str(row["snapshot_json"]))) for row in rows]

    def history(self, *, limit: int = 20) -> ProviderModelRefreshHistory:
        return ProviderModelRefreshHistory(snapshots=self.list_snapshots(limit=limit))


def default_provider_model_refresh_store() -> SQLiteProviderModelRefreshStore:
    return SQLiteProviderModelRefreshStore()


class ProviderModelCacheStatusService:
    def __init__(
        self,
        *,
        settings_loader: SettingsLoader | None = None,
        path_exists: PathExists | None = None,
        url_reachable: UrlReachable | None = None,
        models_root: Path | None = None,
    ) -> None:
        self._settings_loader = settings_loader
        self._path_exists = path_exists or (lambda path: path.exists())
        self._url_reachable = url_reachable or _default_url_reachable
        self._models_root = models_root

    def payload(self) -> ProviderModelCachePayload:
        settings = self._load_settings()
        entries = [
            self._remote_model("llm:openrouter", settings.get("openrouter", {}), "openrouter"),
            self._remote_model("llm:cerebras", settings.get("cerebras", {}), "cerebras"),
            self._llamacpp(settings.get("llamacpp", {})),
            self._local_server_url(
                "server:lmstudio",
                "llm:lmstudio",
                _safe_dict(settings.get("lmstudio")).get("base_url"),
                "settings.lmstudio.base_url",
            ),
            self._local_server_url(
                "server:llamacpp",
                "llm:llamacpp",
                _safe_dict(settings.get("llamacpp")).get("base_url"),
                "settings.llamacpp.base_url",
            ),
            self._configured_model(
                "tts:faster-qwen3-tts",
                "tts:faster-qwen3-tts",
                str(_safe_dict(settings.get("faster-qwen3-tts")).get("model_name") or ""),
                _safe_dict(settings.get("faster-qwen3-tts")).get("model_dir"),
                "settings.faster-qwen3-tts",
            ),
            self._configured_model(
                "image:flux_klein",
                "image:flux_klein",
                str(_safe_dict(_safe_dict(settings.get("image")).get("flux_klein")).get("repo_id") or ""),
                _safe_dict(_safe_dict(settings.get("image")).get("flux_klein")).get("local_dir"),
                "settings.image.flux_klein",
            ),
            self._configured_model(
                "rpg_visual:flux_klein",
                "rpg_visual:flux_klein",
                str(_safe_dict(_safe_dict(settings.get("rpg_visual")).get("flux_klein")).get("repo_id") or ""),
                _safe_dict(_safe_dict(settings.get("rpg_visual")).get("flux_klein")).get("local_dir"),
                "settings.rpg_visual.flux_klein",
            ),
            self._worker_url("worker:tts", settings.get("tts_worker_url"), "settings.tts_worker_url"),
            self._worker_url("worker:stt", settings.get("stt_worker_url"), "settings.stt_worker_url"),
            self._worker_url("worker:image", settings.get("image_worker_url"), "settings.image_worker_url"),
        ]
        diagnostics = [item for entry in entries for item in entry.diagnostics]
        return ProviderModelCachePayload(
            status="degraded" if diagnostics else "ready",
            entries=entries,
            diagnostics=diagnostics,
        )

    def _load_settings(self) -> dict[str, Any]:
        if self._settings_loader:
            return self._settings_loader()
        from app.shared import load_settings

        return load_settings()

    def _models_root_path(self) -> Path:
        return self._models_root or resources_models_root()

    def _remote_model(self, provider_id: str, settings: Any, source: str) -> ProviderModelCacheEntry:
        model_id = str(_safe_dict(settings).get("model") or "")
        return ProviderModelCacheEntry(
            id=f"{provider_id}:model",
            provider_id=provider_id,
            model_id=model_id,
            status="configured" if model_id else "not_configured",
            source=f"settings.{source}",
        )

    def _llamacpp(self, settings: Any) -> ProviderModelCacheEntry:
        data = _safe_dict(settings)
        model_id = str(data.get("model") or "")
        download_location = str(data.get("download_location") or "server")
        path = self._models_root_path() / download_location / model_id if model_id else None
        return self._configured_model("llm:llamacpp", "llm:llamacpp", model_id, path, "settings.llamacpp")

    def _configured_model(
        self,
        entry_id: str,
        provider_id: str,
        model_id: str,
        path_value: Any,
        source: str,
    ) -> ProviderModelCacheEntry:
        path = Path(str(path_value)) if path_value else None
        if not model_id and path is None:
            return ProviderModelCacheEntry(id=entry_id, provider_id=provider_id, status="not_configured", source=source)
        if path is not None:
            exists = self._path_exists(path)
            return ProviderModelCacheEntry(
                id=entry_id,
                provider_id=provider_id,
                model_id=model_id,
                status="available" if exists else "missing_path",
                source=source,
                path=str(path),
                diagnostics=[] if exists else [{"kind": "configured_path_missing", "id": entry_id, "path": str(path)}],
            )
        return ProviderModelCacheEntry(
            id=entry_id,
            provider_id=provider_id,
            model_id=model_id,
            status="configured",
            source=source,
        )

    def _worker_url(self, entry_id: str, value: Any, source: str) -> ProviderModelCacheEntry:
        url = str(value or "").strip()
        if url and not self._url_reachable(url):
            return ProviderModelCacheEntry(
                id=entry_id,
                provider_id=entry_id,
                status="unreachable",
                source=source,
                path=url,
                diagnostics=[{"kind": "configured_server_unreachable", "id": entry_id, "url": url}],
            )
        return ProviderModelCacheEntry(
            id=entry_id,
            provider_id=entry_id,
            status="configured" if url else "not_configured",
            source=source,
            path=url or None,
        )

    def _local_server_url(
        self,
        entry_id: str,
        provider_id: str,
        value: Any,
        source: str,
    ) -> ProviderModelCacheEntry:
        url = str(value or "").strip()
        if not url:
            return ProviderModelCacheEntry(id=entry_id, provider_id=provider_id, status="not_configured", source=source)
        if not self._url_reachable(url):
            return ProviderModelCacheEntry(
                id=entry_id,
                provider_id=provider_id,
                status="unreachable",
                source=source,
                path=url,
                diagnostics=[{"kind": "configured_server_unreachable", "id": entry_id, "url": url}],
            )
        return ProviderModelCacheEntry(
            id=entry_id,
            provider_id=provider_id,
            status="configured",
            source=source,
            path=url,
        )


def get_provider_model_cache_status() -> ProviderModelCachePayload:
    return ProviderModelCacheStatusService().payload()


def create_provider_model_refresh_job_request(request: ProviderModelRefreshRequest) -> CreateJobRequest:
    stages = [
        JobStage(
            id="discover-providers",
            label="Discover providers",
            resource_class=ResourceClass.CPU,
        ),
        JobStage(
            id="discover-local-models",
            label="Discover local models",
            resource_class=ResourceClass.CPU,
        ),
        JobStage(
            id="publish-cache-status",
            label="Publish provider/model cache status",
            resource_class=ResourceClass.CPU,
        ),
    ]
    return CreateJobRequest(
        module="platform",
        type="providers.models.refresh",
        resource_class=ResourceClass.CPU,
        priority=request.priority,
        stages=stages,
        input_payload={
            "scope": request.scope,
            "reason": request.reason,
        },
        compat={
            "contract": "provider_model_refresh_v1",
            "event_families": ["job.created", "job.updated", "job.completed", "job.failed", "job.canceled"],
        },
    )


def create_provider_model_refresh_handlers(
    store: SQLiteProviderModelRefreshStore,
    *,
    provider_facade_factory: ProviderFacadeFactory = default_provider_facade,
    cache_status_factory: CacheStatusFactory = get_provider_model_cache_status,
) -> dict[str, JobHandler]:
    return {
        "providers.models.refresh": lambda job: _handle_provider_model_refresh_job(
            job,
            store,
            provider_facade_factory=provider_facade_factory,
            cache_status_factory=cache_status_factory,
        )
    }


def _handle_provider_model_refresh_job(
    job: JobRecord,
    store: SQLiteProviderModelRefreshStore,
    *,
    provider_facade_factory: ProviderFacadeFactory,
    cache_status_factory: CacheStatusFactory,
) -> dict[str, Any]:
    payload = job.input_payload or {}
    scope = _safe_refresh_scope(payload.get("scope"))
    reason = _safe_optional_str(payload.get("reason"))
    provider_payload = provider_facade_factory().payload()
    cache_payload = cache_status_factory()
    snapshot = store.record_snapshot(
        scope=scope,
        reason=reason,
        provider_payload=provider_payload,
        cache_payload=cache_payload,
    )
    return {
        "logs": [
            {
                "level": "info",
                "message": "provider/model refresh completed",
                "snapshot_id": snapshot.id,
                "scope": snapshot.scope,
                "provider_count": snapshot.provider_count,
                "model_count": snapshot.model_count,
                "cache_status": snapshot.cache_status,
            }
        ],
        "output_refs": [
            {
                "kind": "provider_model_refresh",
                "snapshot_id": snapshot.id,
                "scope": snapshot.scope,
                "provider_count": snapshot.provider_count,
                "model_count": snapshot.model_count,
                "cache_status": snapshot.cache_status,
                "status": snapshot.status,
            }
        ],
    }


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_optional_str(value: Any) -> str | None:
    text = _safe_str(value).strip()
    return text or None


def _safe_refresh_scope(value: Any) -> RefreshScope:
    text = _safe_str(value).strip()
    if text in {"providers", "models", "all"}:
        return text  # type: ignore[return-value]
    return "all"


def _payload_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value if isinstance(value, dict) else {}


def _json_loads(value: str) -> dict[str, Any]:
    data = json.loads(value)
    return data if isinstance(data, dict) else {}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_url_reachable(url: str, timeout_seconds: float = 0.2) -> bool:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    host = parsed.hostname
    port = parsed.port
    if not host:
        return False
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False
