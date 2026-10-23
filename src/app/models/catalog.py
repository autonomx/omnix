"""Model catalog v2 (desktop roadmap §4.6): models, runtime packs and capability bundles.

``catalog.json`` is the one list of models Omnix installs. Each model names its
Hugging Face repository, a pinned commit, the SHA-256 and size of every file a
service reads, its licence and terms, and what it is for. Runtime packs are the
Python environments the model services run in (a shared Torch layer and
per-service overlays, roadmap §4.3); bundles are what the setup screen offers:
one capability, with a variant per platform naming its models and runtimes.

Models that their own package fetches on first use (``source: "package"``)
have no pinned files; Voice Studio lists them, and no bundle installs them.
"""
from __future__ import annotations

import json
import platform as _platform
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).with_name("catalog.json")
REVISION_LENGTH = 40
PLATFORMS = ("windows-x64", "macos-arm64", "macos-x64", "linux-x64")
RUNTIME_KINDS = ("torch-layer", "overlay", "standalone")


class CatalogError(ValueError):
    """The catalog is malformed: a model, runtime or bundle is missing a field or names something unknown."""


@dataclass(frozen=True)
class ModelFile:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class Licence:
    id: str = ""
    url: str = ""
    commercial_use: bool = True
    gated: bool = False
    output_terms: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "url": self.url, "commercial_use": self.commercial_use, "gated": self.gated,
                "output_terms": self.output_terms}


@dataclass(frozen=True)
class ModelEntry:
    id: str
    repo: str
    revision: str
    service: str
    files: tuple[ModelFile, ...]
    label: str = ""
    kind: str = ""
    source: str = "huggingface"
    licence: Licence = field(default_factory=Licence)
    vram_gb: float = 0.0
    residency: str = "helper"
    capabilities: tuple[str, ...] = ()
    voice_studio: bool = False
    aliases: tuple[str, ...] = ()
    legacy_folder: str = ""

    @property
    def size(self) -> int:
        return sum(item.size for item in self.files)

    @property
    def pinned(self) -> bool:
        """Installable by Omnix: files and a full commit to check them against."""
        return self.source == "huggingface" and bool(self.files)

    @property
    def folder_name(self) -> str:
        """The folder Voice Studio's layout uses (``resources/models/<kind>/<name>``)."""
        return self.legacy_folder or self.repo.split("/")[-1]


@dataclass(frozen=True)
class RuntimePack:
    id: str
    label: str
    kind: str
    platform: str
    accelerator: str
    lock: str
    files: str
    base: str = ""
    service: str = ""
    source_lock: str = ""
    requires: Mapping[str, str] = field(default_factory=dict)
    licences: tuple[str, ...] = ()


@dataclass(frozen=True)
class BundleOption:
    """A model the user may add to a bundle (another voice engine, another image model)."""

    model: str
    runtimes: tuple[str, ...] = ()
    default: bool = False
    # Its own load requirements (an image model, a voice engine's child process); None: not measured.
    min_vram_mb: int | None = None
    min_commit_mb: int | None = None
    note: str = ""


@dataclass(frozen=True)
class BundleVariant:
    platform: str
    accelerator: str
    models: tuple[str, ...]
    runtimes: tuple[str, ...]
    min_vram_mb: int | None = None
    min_commit_mb: int | None = None
    note: str = ""
    options: tuple[BundleOption, ...] = ()
    # How many options the bundle needs (image generation needs a model to generate with).
    min_options: int = 0

    def option(self, model_id: str) -> BundleOption | None:
        return next((item for item in self.options if item.model == model_id), None)

    def default_options(self) -> tuple[str, ...]:
        return tuple(item.model for item in self.options if item.default)

    def chosen(self, picked: Iterable[str] | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """(models, runtimes) for the required models and the picked options (the defaults when none are named)."""
        names = list(self.default_options() if picked is None else picked)
        unknown = [name for name in names if self.option(name) is None]
        if unknown:
            raise CatalogError(f"not an option of this bundle: {', '.join(unknown)}")
        options = [item for item in self.options if item.model in names]
        models = (*self.models, *(item.model for item in options))
        runtimes = list(self.runtimes)
        for item in options:
            runtimes.extend(runtime for runtime in item.runtimes if runtime not in runtimes)
        return models, tuple(runtimes)

    def all_models(self) -> tuple[str, ...]:
        return (*self.models, *(item.model for item in self.options))

    def installed_options(self, has_model: Callable[[str], bool],
                          has_runtime: Callable[[str], bool] = lambda runtime_id: True) -> tuple[str, ...]:
        return tuple(item.model for item in self.options
                     if has_model(item.model) and all(has_runtime(runtime_id) for runtime_id in item.runtimes))

    def satisfied(self, has_model: Callable[[str], bool]) -> bool:
        """Its required models are installed, and enough of its options (runtimes are checked by the caller)."""
        return (all(has_model(model_id) for model_id in self.models)
                and len(self.installed_options(has_model)) >= self.min_options)


@dataclass(frozen=True)
class Bundle:
    id: str
    label: str
    capability: str
    description: str
    recommended_rank: int
    variants: tuple[BundleVariant, ...]

    def variant(self, platform: str) -> BundleVariant | None:
        return next((item for item in self.variants if item.platform == platform), None)


@dataclass(frozen=True)
class Catalog:
    models: Mapping[str, ModelEntry]
    runtimes: Mapping[str, RuntimePack]
    bundles: Mapping[str, Bundle]
    version: int = 2

    def model(self, model_id: str) -> ModelEntry:
        """A model by its id or one of its aliases (ids the catalogs used before they were merged)."""
        found = self.models.get(model_id)
        if found is not None:
            return found
        for entry in self.models.values():
            if model_id in entry.aliases:
                return entry
        raise KeyError(f"unknown model: {model_id}")

    def canonical_id(self, model_id: str) -> str:
        return self.model(model_id).id

    def runtime(self, runtime_id: str) -> RuntimePack:
        try:
            return self.runtimes[runtime_id]
        except KeyError:
            raise KeyError(f"unknown runtime: {runtime_id}") from None

    def bundle(self, bundle_id: str) -> Bundle:
        try:
            return self.bundles[bundle_id]
        except KeyError:
            raise KeyError(f"unknown bundle: {bundle_id}") from None

    def runtime_closure(self, runtime_ids: Iterable[str]) -> list[RuntimePack]:
        """The runtimes and every base they stand on, bases first."""
        ordered: list[RuntimePack] = []

        def visit(runtime_id: str) -> None:
            pack = self.runtime(runtime_id)
            if pack.base:
                visit(pack.base)
            if pack not in ordered:
                ordered.append(pack)

        for runtime_id in runtime_ids:
            visit(runtime_id)
        return ordered

    def dependents(self, runtime_id: str) -> list[str]:
        """Runtimes that stand on ``runtime_id``."""
        return [pack.id for pack in self.runtimes.values() if pack.base == runtime_id]

    def runtimes_for_model(self, model_id: str, platform: str) -> list[str]:
        """The runtimes a model runs in on ``platform``: those of the bundles that install it there."""
        canonical = self.canonical_id(model_id)
        found: list[str] = []
        for bundle in self.bundles.values():
            variant = bundle.variant(platform)
            if variant is None:
                continue
            option = variant.option(canonical)
            if canonical in variant.models or option is not None:
                runtimes = (*variant.runtimes, *(option.runtimes if option is not None else ()))
                found.extend(item for item in runtimes if item not in found)
        return found


def current_platform() -> str:
    machine = _platform.machine().lower()
    arm = machine in {"arm64", "aarch64"}
    if sys.platform == "win32":
        return "windows-x64"
    if sys.platform == "darwin":
        return "macos-arm64" if arm else "macos-x64"
    return "linux-x64"


def _require(raw: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in raw:
        raise CatalogError(f"{where}: missing {key!r}")
    return raw[key]


def _model(model_id: str, raw: Mapping[str, Any]) -> ModelEntry:
    where = f"model {model_id}"
    source = str(raw.get("source") or "huggingface")
    if source not in {"huggingface", "package"}:
        raise CatalogError(f"{where}: source must be huggingface or package")
    revision = str(_require(raw, "revision", where))
    files = tuple(
        ModelFile(path=name, sha256=str(item["sha256"]), size=int(item["size"]))
        for name, item in sorted(dict(raw.get("files") or {}).items())
    )
    if source == "huggingface":
        if len(revision) != REVISION_LENGTH or any(char not in "0123456789abcdef" for char in revision):
            raise CatalogError(f"{model_id}: revision must be a full commit hash")
        if not files:
            raise CatalogError(f"{model_id}: no files listed")
        bad = [item.path for item in files if len(item.sha256) != 64 or item.size <= 0]
        if bad:
            raise CatalogError(f"{model_id}: files without a SHA-256 and size: {bad}")
    licence = dict(raw.get("licence") or {})
    return ModelEntry(
        id=model_id,
        repo=str(_require(raw, "repo", where)),
        revision=revision,
        service=str(_require(raw, "service", where)),
        files=files,
        label=str(raw.get("label") or model_id),
        kind=str(raw.get("kind") or raw.get("service") or ""),
        source=source,
        licence=Licence(
            id=str(licence.get("id") or ""),
            url=str(licence.get("url") or ""),
            commercial_use=bool(licence.get("commercial_use", True)),
            gated=bool(licence.get("gated", False)),
            output_terms=str(licence.get("output_terms") or ""),
        ),
        vram_gb=float(raw.get("vram_gb") or 0.0),
        residency=str(raw.get("residency") or "helper"),
        capabilities=tuple(str(item) for item in raw.get("capabilities") or ()),
        voice_studio=bool(raw.get("voice_studio", False)),
        aliases=tuple(str(item) for item in raw.get("aliases") or ()),
        legacy_folder=str(raw.get("legacy_folder") or ""),
    )


def _runtime(runtime_id: str, raw: Mapping[str, Any]) -> RuntimePack:
    where = f"runtime {runtime_id}"
    kind = str(_require(raw, "kind", where))
    if kind not in RUNTIME_KINDS:
        raise CatalogError(f"{where}: kind must be one of {RUNTIME_KINDS}")
    platform = str(_require(raw, "platform", where))
    if platform not in PLATFORMS:
        raise CatalogError(f"{where}: unknown platform {platform!r}")
    base = str(raw.get("base") or "")
    if kind == "overlay" and not base:
        raise CatalogError(f"{where}: an overlay needs a base")
    return RuntimePack(
        id=runtime_id,
        label=str(raw.get("label") or runtime_id),
        kind=kind,
        platform=platform,
        accelerator=str(raw.get("accelerator") or ""),
        lock=str(_require(raw, "lock", where)),
        files=str(_require(raw, "files", where)),
        base=base,
        service=str(raw.get("service") or ""),
        source_lock=str(raw.get("source_lock") or ""),
        requires={str(key): str(value) for key, value in dict(raw.get("requires") or {}).items()},
        licences=tuple(str(item) for item in raw.get("licences") or ()),
    )


def _option(raw: Mapping[str, Any], where: str) -> BundleOption:
    return BundleOption(
        model=str(_require(raw, "model", where)),
        runtimes=tuple(str(runtime) for runtime in raw.get("runtimes") or ()),
        default=bool(raw.get("default")),
        min_vram_mb=None if raw.get("min_vram_mb") is None else int(raw["min_vram_mb"]),
        min_commit_mb=None if raw.get("min_commit_mb") is None else int(raw["min_commit_mb"]),
        note=str(raw.get("note") or ""),
    )


def _bundle(bundle_id: str, raw: Mapping[str, Any]) -> Bundle:
    where = f"bundle {bundle_id}"
    variants = []
    for item in _require(raw, "variants", where):
        platform = str(_require(item, "platform", where))
        if platform not in PLATFORMS:
            raise CatalogError(f"{where}: unknown platform {platform!r}")
        variants.append(BundleVariant(
            platform=platform,
            accelerator=str(item.get("accelerator") or ""),
            models=tuple(str(model) for model in _require(item, "models", where)),
            runtimes=tuple(str(runtime) for runtime in item.get("runtimes") or ()),
            min_vram_mb=None if item.get("min_vram_mb") is None else int(item["min_vram_mb"]),
            min_commit_mb=None if item.get("min_commit_mb") is None else int(item["min_commit_mb"]),
            note=str(item.get("note") or ""),
            options=tuple(_option(option, where) for option in item.get("options") or ()),
            min_options=int(item.get("min_options") or 0),
        ))
        if variants[-1].min_options > len(variants[-1].default_options()):
            raise CatalogError(f"{where}: {platform} needs {variants[-1].min_options} options, but fewer are defaults")
    platforms = [item.platform for item in variants]
    if len(platforms) != len(set(platforms)):
        raise CatalogError(f"{where}: one variant per platform")
    return Bundle(
        id=bundle_id,
        label=str(raw.get("label") or bundle_id),
        capability=str(_require(raw, "capability", where)),
        description=str(raw.get("description") or ""),
        recommended_rank=int(raw.get("recommended_rank") or 99),
        variants=tuple(variants),
    )


def parse_catalog(raw: Mapping[str, Any]) -> Catalog:
    """A catalog from its JSON. Version 1 files (``models`` only, without metadata) still load."""
    models = {model_id: _model(model_id, entry) for model_id, entry in dict(raw.get("models") or {}).items()}
    names: dict[str, str] = {}
    for entry in models.values():
        for name in (entry.id, *entry.aliases):
            if name in names and names[name] != entry.id:
                raise CatalogError(f"{name!r} names both {names[name]} and {entry.id}")
            names[name] = entry.id
    runtimes = {runtime_id: _runtime(runtime_id, entry) for runtime_id, entry in dict(raw.get("runtimes") or {}).items()}
    for pack in runtimes.values():
        if pack.base:
            base = runtimes.get(pack.base)
            if base is None:
                raise CatalogError(f"runtime {pack.id}: unknown base {pack.base!r}")
            if base.kind != "torch-layer" or base.platform != pack.platform:
                raise CatalogError(f"runtime {pack.id}: its base must be a Torch layer for {pack.platform}")
    bundles = {bundle_id: _bundle(bundle_id, entry) for bundle_id, entry in dict(raw.get("bundles") or {}).items()}
    for bundle in bundles.values():
        for variant in bundle.variants:
            for model_id in variant.all_models():
                entry = models.get(names.get(model_id, ""))
                if entry is None:
                    raise CatalogError(f"bundle {bundle.id}: unknown model {model_id!r}")
                if not entry.pinned:
                    raise CatalogError(f"bundle {bundle.id}: {model_id} has no pinned files")
            for runtime_id in (*variant.runtimes, *(runtime for item in variant.options for runtime in item.runtimes)):
                pack = runtimes.get(runtime_id)
                if pack is None:
                    raise CatalogError(f"bundle {bundle.id}: unknown runtime {runtime_id!r}")
                if pack.platform != variant.platform:
                    raise CatalogError(f"bundle {bundle.id}: runtime {runtime_id} is not for {variant.platform}")
    return Catalog(models=models, runtimes=runtimes, bundles=bundles, version=int(raw.get("catalog_version") or 1))


_CACHE: dict[Path, tuple[float, Catalog]] = {}


def load(path: Path = CATALOG_PATH) -> Catalog:
    """The catalog at ``path``, re-read when the file changes."""
    resolved = path.resolve()
    stamp = resolved.stat().st_mtime
    cached = _CACHE.get(resolved)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    catalog = parse_catalog(json.loads(resolved.read_text(encoding="utf-8")))
    _CACHE[resolved] = (stamp, catalog)
    return catalog


__all__ = [
    "CATALOG_PATH", "Bundle", "BundleOption", "BundleVariant", "Catalog", "CatalogError", "Licence", "ModelEntry", "ModelFile",
    "PLATFORMS", "RuntimePack", "current_platform", "load", "parse_catalog",
]
