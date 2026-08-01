"""Governed Live2D catalog, local installer, and Character avatar activation."""
from __future__ import annotations

import json
import mimetypes
import posixpath
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.assets import AssetRecord, AssetType, SharedAssetStore, default_asset_store
from app.runtime_paths import resources_data_root

from .avatar_models import CharacterAvatarPack, UpsertCharacterAvatarPackRequest
from .avatar_service import CharacterAvatarService, default_character_avatar_service
from .repository import CharacterNotFoundError

OPEN_LLM_VTUBER_REVISION = "992309c0aa19845960228f880013d4685fde93b5"
OPEN_LLM_VTUBER_WEB_REVISION = "d176e7df2366952e3bacbf12cf9a8b18a4315932"
MAX_LIVE2D_FILE_BYTES = 64 * 1024 * 1024

_RUNTIME_FILES = {
    "pixi.min.js": "https://cdnjs.cloudflare.com/ajax/libs/pixi.js/6.5.10/browser/pixi.min.js",
    "live2dcubismcore.min.js": (
        "https://raw.githubusercontent.com/Open-LLM-VTuber/Open-LLM-VTuber-Web/"
        f"{OPEN_LLM_VTUBER_WEB_REVISION}/src/renderer/WebSDK/Core/live2dcubismcore.min.js"
    ),
    "cubism4.min.js": "https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/dist/cubism4.min.js",
}

_MODEL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "open-llm-vtuber-mao-pro",
        "name": "Niziiro Mao (PRO)",
        "description": "Expressive front-facing Cubism 5 sample with idle motion, expressions, and VTuber-oriented face movement.",
        "preview_url": "https://raw.githubusercontent.com/Open-LLM-VTuber/Open-LLM-VTuber/992309c0aa19845960228f880013d4685fde93b5/assets/i1.jpg",
        "repository": "Open-LLM-VTuber/Open-LLM-VTuber",
        "revision": OPEN_LLM_VTUBER_REVISION,
        "entry_path": "live2d-models/mao_pro/runtime/mao_pro.model3.json",
        "source_url": "https://github.com/Open-LLM-VTuber/Open-LLM-VTuber",
        "model_license_url": "https://www.live2d.com/en/download/sample-data/",
        "runtime_license_url": "https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html",
        "license_summary": "Live2D sample data. Separate Live2D terms apply; commercial rights depend on user or organization classification.",
        "mouth_parameter_ids": ["ParamA", "ParamMouthOpenY", "PARAM_MOUTH_OPEN_Y"],
        "mouth_form_parameter_ids": ["ParamMouthForm", "PARAM_MOUTH_FORM"],
    },
    {
        "id": "open-llm-vtuber-shizuku",
        "name": "Shizuku (PRO)",
        "description": "Classic expressive Live2D sample with multiple textures, idle motion, physics, pose, and lip-sync parameters.",
        "preview_url": "https://raw.githubusercontent.com/Open-LLM-VTuber/Open-LLM-VTuber/992309c0aa19845960228f880013d4685fde93b5/assets/i2.jpg",
        "repository": "Open-LLM-VTuber/Open-LLM-VTuber",
        "revision": OPEN_LLM_VTUBER_REVISION,
        "entry_path": "live2d-models/shizuku/runtime/shizuku.model3.json",
        "source_url": "https://github.com/Open-LLM-VTuber/Open-LLM-VTuber",
        "model_license_url": "https://www.live2d.com/en/download/sample-data/",
        "runtime_license_url": "https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html",
        "license_summary": "Live2D sample data. Separate Live2D terms apply; commercial rights depend on user or organization classification.",
        "mouth_parameter_ids": ["PARAM_MOUTH_OPEN_Y", "ParamMouthOpenY", "ParamA"],
        "mouth_form_parameter_ids": ["PARAM_MOUTH_FORM", "ParamMouthForm"],
    },
)


class Live2DModelCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    preview_url: str
    repository: str
    revision: str
    source_url: str
    model_license_url: str
    runtime_license_url: str
    license_summary: str
    installed: bool = False
    selected: bool = False


class Live2DModelCatalogResponse(BaseModel):
    models: list[Live2DModelCatalogItem]
    runtime_installed: bool = False


class ActivateLive2DAvatarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=160)
    accept_live2d_runtime_terms: bool = False
    accept_model_terms: bool = False


class Live2DAvatarActionResponse(BaseModel):
    ok: bool = True
    character_id: str
    avatar_pack: CharacterAvatarPack | None = None
    downloaded: bool = False


DownloadBytes = Callable[[str], bytes]


class CharacterLive2DAvatarService:
    def __init__(
        self,
        *,
        avatar_service_factory: Callable[[], CharacterAvatarService] = default_character_avatar_service,
        asset_store_factory: Callable[[], SharedAssetStore] = default_asset_store,
        data_root: str | Path | None = None,
        download_bytes: DownloadBytes | None = None,
    ) -> None:
        self.avatar_service_factory = avatar_service_factory
        self.asset_store_factory = asset_store_factory
        self.data_root = Path(data_root) if data_root is not None else resources_data_root() / "character_live2d"
        self.download_bytes = download_bytes or _download_bytes

    @property
    def runtime_root(self) -> Path:
        return self.data_root / "runtime"

    @property
    def models_root(self) -> Path:
        return self.data_root / "models"

    def catalog(self, character_id: str) -> Live2DModelCatalogResponse:
        current = self.avatar_service_factory().optional_get(character_id)
        assets = {asset.id: asset for asset in self.asset_store_factory().list_assets().assets}
        models = []
        for entry in _MODEL_CATALOG:
            asset_id = _asset_id(entry["id"])
            asset = assets.get(asset_id)
            installed = bool(asset and Path(asset.storage_path).is_file())
            models.append(
                Live2DModelCatalogItem(
                    **{key: value for key, value in entry.items() if key not in {"entry_path", "mouth_parameter_ids", "mouth_form_parameter_ids"}},
                    installed=installed,
                    selected=bool(current and current.renderer == "live2d" and current.rig_asset_id == asset_id),
                )
            )
        return Live2DModelCatalogResponse(
            models=models,
            runtime_installed=all((self.runtime_root / filename).is_file() for filename in _RUNTIME_FILES),
        )

    def activate(
        self,
        character_id: str,
        request: ActivateLive2DAvatarRequest,
    ) -> Live2DAvatarActionResponse:
        if not request.accept_live2d_runtime_terms or not request.accept_model_terms:
            raise ValueError("Live2D runtime and sample-model terms must be accepted before download or activation")
        entry = _catalog_entry(request.model_id)
        avatar_service = self.avatar_service_factory()
        current = avatar_service.optional_get(character_id)
        asset, downloaded = self._ensure_model_asset(entry)
        self._remember_previous_pack(asset, current, character_id)
        request_payload = UpsertCharacterAvatarPackRequest(
            expected_version=current.version if current else None,
            render_mode="viseme",
            renderer="live2d",
            rig_asset_id=asset.id,
            mouth_anchor={"x": 0.5, "y": 0.68},
        )
        pack = avatar_service.upsert(character_id, request_payload)
        return Live2DAvatarActionResponse(
            character_id=character_id,
            avatar_pack=pack,
            downloaded=downloaded,
        )

    def disable(self, character_id: str) -> Live2DAvatarActionResponse:
        avatar_service = self.avatar_service_factory()
        current = avatar_service.optional_get(character_id)
        if current is None:
            return Live2DAvatarActionResponse(character_id=character_id, avatar_pack=None)
        if current.renderer != "live2d" or not current.rig_asset_id:
            return Live2DAvatarActionResponse(character_id=character_id, avatar_pack=current)

        asset = self.asset_store_factory().get_asset(current.rig_asset_id)
        previous_payload = None
        if asset is not None:
            previous_payload = dict(asset.metadata or {}).get("previous_packs", {}).get(character_id)
        if isinstance(previous_payload, dict):
            previous_payload = dict(previous_payload)
            previous_payload.pop("character_id", None)
            previous_payload.pop("version", None)
            previous_payload.pop("created_at", None)
            previous_payload.pop("updated_at", None)
            previous_payload["expected_version"] = current.version
            restored = avatar_service.upsert(character_id, UpsertCharacterAvatarPackRequest.model_validate(previous_payload))
            return Live2DAvatarActionResponse(character_id=character_id, avatar_pack=restored)

        avatar_service.delete(character_id)
        return Live2DAvatarActionResponse(character_id=character_id, avatar_pack=None)

    def runtime_file(self, filename: str) -> Path:
        if filename not in _RUNTIME_FILES:
            raise FileNotFoundError(filename)
        path = self.runtime_root / filename
        if not path.is_file():
            raise FileNotFoundError(filename)
        return path

    def model_file(self, asset_id: str, asset_path: str) -> Path:
        asset = self.asset_store_factory().get_asset(asset_id)
        if asset is None or asset.module != "character-live2d" or asset.type != AssetType.SETTINGS_ARTIFACT:
            raise FileNotFoundError(asset_id)
        root_value = str(dict(asset.metadata or {}).get("root_path") or "")
        root = Path(root_value) if root_value else Path(asset.storage_path).parent
        root = root.resolve()
        requested = (root / _safe_relative_path(asset_path)).resolve()
        if requested != root and root not in requested.parents:
            raise FileNotFoundError(asset_path)
        if not requested.is_file():
            raise FileNotFoundError(asset_path)
        return requested

    def _ensure_model_asset(self, entry: dict[str, Any]) -> tuple[AssetRecord, bool]:
        self._ensure_runtime()
        asset_store = self.asset_store_factory()
        asset_id = _asset_id(entry["id"])
        existing = asset_store.get_asset(asset_id)
        if existing is not None and Path(existing.storage_path).is_file():
            return existing, False

        model_root = self.models_root / entry["id"]
        entry_relative = _model_relative_path(entry)
        entry_target = model_root / entry_relative
        entry_bytes = self._write_remote_file(_raw_model_url(entry, entry_relative), entry_target)
        try:
            model_json = json.loads(entry_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid Live2D model descriptor for {entry['id']}") from exc

        entry_dir = PurePosixPath(entry_relative).parent
        for referenced_path in _model_references(model_json):
            resolved_relative = _safe_relative_path(str(entry_dir / referenced_path))
            self._write_remote_file(
                _raw_model_url(entry, resolved_relative),
                model_root / resolved_relative,
            )

        now = _utcnow()
        asset = AssetRecord(
            id=asset_id,
            module="character-live2d",
            type=AssetType.SETTINGS_ARTIFACT,
            mime_type="application/vnd.live2d.model3+json",
            storage_path=str(entry_target),
            metadata={
                "model_id": entry["id"],
                "display_name": entry["name"],
                "root_path": str(model_root),
                "entry_path": entry_relative,
                "repository": entry["repository"],
                "revision": entry["revision"],
                "source_url": entry["source_url"],
                "model_license_url": entry["model_license_url"],
                "runtime_license_url": entry["runtime_license_url"],
                "license_summary": entry["license_summary"],
                "mouth_parameter_ids": list(entry["mouth_parameter_ids"]),
                "mouth_form_parameter_ids": list(entry["mouth_form_parameter_ids"]),
                "runtime_files": list(_RUNTIME_FILES),
                "previous_packs": {},
            },
            created_at=now,
            compat={"source_project": "Open-LLM-VTuber", "source_revision": entry["revision"]},
        )
        asset_store.upsert_asset(asset)
        return asset, True

    def _ensure_runtime(self) -> None:
        for filename, url in _RUNTIME_FILES.items():
            path = self.runtime_root / filename
            if not path.is_file():
                self._write_remote_file(url, path)

    def _write_remote_file(self, url: str, target: Path) -> bytes:
        if target.is_file():
            return target.read_bytes()
        data = self.download_bytes(url)
        if len(data) > MAX_LIVE2D_FILE_BYTES:
            raise ValueError(f"Live2D download exceeds {MAX_LIVE2D_FILE_BYTES} bytes: {url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f"{target.suffix}.partial")
        temporary.write_bytes(data)
        temporary.replace(target)
        return data

    def _remember_previous_pack(
        self,
        target_asset: AssetRecord,
        current: CharacterAvatarPack | None,
        character_id: str,
    ) -> None:
        previous_payload: dict[str, Any] | None = None
        if current is not None and current.renderer != "live2d":
            previous_payload = current.model_dump(mode="json")
        elif current is not None and current.rig_asset_id:
            current_asset = self.asset_store_factory().get_asset(current.rig_asset_id)
            if current_asset is not None:
                candidate = dict(current_asset.metadata or {}).get("previous_packs", {}).get(character_id)
                if isinstance(candidate, dict):
                    previous_payload = dict(candidate)
        if previous_payload is None:
            return
        metadata = dict(target_asset.metadata or {})
        previous_packs = dict(metadata.get("previous_packs") or {})
        previous_packs[character_id] = previous_payload
        metadata["previous_packs"] = previous_packs
        self.asset_store_factory().upsert_asset(target_asset.model_copy(update={"metadata": metadata}))


def register_character_live2d_avatar_routes(
    app: FastAPI,
    *,
    service_factory: Callable[[], CharacterLive2DAvatarService] = CharacterLive2DAvatarService,
) -> None:
    @app.get(
        "/api/characters/{character_id}/live2d-models",
        response_model=Live2DModelCatalogResponse,
        tags=["characters"],
        include_in_schema=False,
    )
    async def live2d_model_catalog(character_id: str) -> Live2DModelCatalogResponse:
        try:
            return service_factory().catalog(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/characters/{character_id}/live2d-avatar",
        response_model=Live2DAvatarActionResponse,
        tags=["characters"],
        include_in_schema=False,
    )
    async def activate_live2d_avatar(
        character_id: str,
        request: ActivateLive2DAvatarRequest,
    ) -> Live2DAvatarActionResponse:
        try:
            return service_factory().activate(character_id, request)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/api/characters/{character_id}/live2d-avatar/disable",
        response_model=Live2DAvatarActionResponse,
        tags=["characters"],
        include_in_schema=False,
    )
    async def disable_live2d_avatar(character_id: str) -> Live2DAvatarActionResponse:
        try:
            return service_factory().disable(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/character-live2d/runtime/{filename}",
        tags=["characters"],
        include_in_schema=False,
    )
    async def live2d_runtime_file(filename: str) -> FileResponse:
        try:
            path = service_factory().runtime_file(filename)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Live2D runtime file not installed") from exc
        media_type = "text/javascript" if path.suffix == ".js" else "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    @app.get(
        "/api/character-live2d/assets/{asset_id}/{asset_path:path}",
        tags=["characters"],
        include_in_schema=False,
    )
    async def live2d_model_file(asset_id: str, asset_path: str) -> FileResponse:
        try:
            path = service_factory().model_file(asset_id, asset_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Live2D model file not found") from exc
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)


def _catalog_entry(model_id: str) -> dict[str, Any]:
    for entry in _MODEL_CATALOG:
        if entry["id"] == model_id:
            return dict(entry)
    raise ValueError(f"unknown Live2D model: {model_id}")


def _asset_id(model_id: str) -> str:
    return f"character-live2d:{model_id}"


def _model_relative_path(entry: dict[str, Any]) -> str:
    marker = "live2d-models/"
    source_path = str(entry["entry_path"])
    if marker not in source_path:
        raise ValueError("Live2D catalog entry is outside live2d-models")
    return _safe_relative_path(source_path.split(marker, 1)[1].split("/", 1)[1])


def _raw_model_url(entry: dict[str, Any], relative_path: str) -> str:
    source_entry = PurePosixPath(str(entry["entry_path"]))
    model_root = source_entry.parents[1]
    repository = str(entry["repository"])
    revision = str(entry["revision"])
    return (
        f"https://raw.githubusercontent.com/{repository}/{revision}/"
        f"{model_root.as_posix()}/{_safe_relative_path(relative_path)}"
    )


def _safe_relative_path(value: str) -> str:
    normalized = posixpath.normpath(str(value).replace("\\", "/")).lstrip("/")
    path = PurePosixPath(normalized)
    if normalized in {"", "."} or ".." in path.parts:
        raise ValueError(f"unsafe Live2D asset path: {value}")
    return path.as_posix()


def _model_references(model_json: dict[str, Any]) -> list[str]:
    references = dict(model_json.get("FileReferences") or {})
    result: list[str] = []
    for key in ("Moc", "Physics", "Pose", "DisplayInfo", "UserData"):
        value = references.get(key)
        if isinstance(value, str) and value:
            result.append(_safe_relative_path(value))
    for value in references.get("Textures") or []:
        if isinstance(value, str) and value:
            result.append(_safe_relative_path(value))
    for value in references.get("Expressions") or []:
        if isinstance(value, dict) and isinstance(value.get("File"), str):
            result.append(_safe_relative_path(value["File"]))
    for motion_group in dict(references.get("Motions") or {}).values():
        for value in motion_group or []:
            if isinstance(value, dict) and isinstance(value.get("File"), str):
                result.append(_safe_relative_path(value["File"]))
            if isinstance(value, dict) and isinstance(value.get("Sound"), str):
                result.append(_safe_relative_path(value["Sound"]))
    return list(dict.fromkeys(result))


def _download_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Omnix-Live2D-Installer/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310 - catalog URLs are fixed above
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length > MAX_LIVE2D_FILE_BYTES:
            raise ValueError(f"Live2D download exceeds {MAX_LIVE2D_FILE_BYTES} bytes: {url}")
        return response.read(MAX_LIVE2D_FILE_BYTES + 1)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "ActivateLive2DAvatarRequest",
    "CharacterLive2DAvatarService",
    "Live2DAvatarActionResponse",
    "Live2DModelCatalogItem",
    "Live2DModelCatalogResponse",
    "register_character_live2d_avatar_routes",
]
