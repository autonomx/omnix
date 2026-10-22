"""What the setup screen offers on this machine: a verdict per bundle (desktop roadmap §4.5).

A bundle is one capability (voice input, voice output, transcription, image
generation). Its verdict for this machine is

- ``fits``: it can be installed and should run well;
- ``warn``: it can be installed, but something is tight (VRAM, memory, a
  requirement not measured yet) and the reason says what;
- ``unavailable``: it cannot run here, with the reason ("needs an NVIDIA GPU",
  "not available on macOS", "update your NVIDIA driver"). Unavailable bundles
  stay visible.

Sizes count only what is not installed yet: the bundle's models and the
runtime packs it stands on (a shared Torch layer is counted once, by
``selection_size``).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.models.catalog import Bundle, BundleVariant, Catalog

NVIDIA_DRIVERS = "https://www.nvidia.com/en-us/drivers/"
# Unpacked runtimes take more room than their downloads; models do not.
RUNTIME_DISK_FACTOR = 3.5


@dataclass(frozen=True)
class Installed:
    """What is already on disk: runtime and model ids."""

    runtimes: frozenset[str] = frozenset()
    models: frozenset[str] = frozenset()


@dataclass
class Verdict:
    bundle: str
    label: str
    description: str
    capability: str
    status: str
    reasons: list[str] = field(default_factory=list)
    action: dict[str, str] | None = None
    models: list[str] = field(default_factory=list)
    runtimes: list[str] = field(default_factory=list)
    installed: bool = False
    model_bytes: int = 0
    runtime_bytes: int = 0
    recommended: bool = False
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _version(text: str) -> tuple[int, ...]:
    parts = []
    for piece in text.split("."):
        digits = "".join(char for char in piece if char.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _gpu_reasons(variant: BundleVariant, runtimes: Iterable[Any], facts: Mapping[str, Any]) -> tuple[str, list[str], dict | None]:
    """(status, reasons, action) for the variant's accelerator on this machine."""
    if variant.accelerator == "cuda":
        gpus = [gpu for gpu in facts.get("gpus") or [] if gpu.get("vendor") == "nvidia"]
        if not gpus:
            others = [item["name"] for item in facts.get("adapters") or [] if item.get("vendor") != "nvidia"]
            detail = f" (found {', '.join(others)})" if others else ""
            return "unavailable", [f"Needs an NVIDIA GPU{detail}."], None
        driver = str(facts.get("nvidia_driver") or gpus[0].get("driver") or "")
        for pack in runtimes:
            minimum = pack.requires.get("nvidia_driver_min")
            if minimum and driver and _version(driver) < _version(minimum):
                return "unavailable", [f"Update your NVIDIA driver: {driver} is installed, {minimum} or newer is "
                                       "needed."], {"label": "Get the NVIDIA driver", "url": NVIDIA_DRIVERS}
        best = max(gpus, key=lambda gpu: gpu.get("vram_total_mb") or 0)
        if variant.min_vram_mb is not None:
            total = best.get("vram_total_mb") or 0
            free = best.get("vram_free_mb")
            need_gb = variant.min_vram_mb / 1024
            if total < variant.min_vram_mb:
                return "warn", [f"Needs about {need_gb:.0f} GB of video memory; {best['name']} has "
                                f"{total / 1024:.0f} GB, so it will run slowly or not at all."], None
            if free is not None and free < variant.min_vram_mb:
                return "warn", [f"Tight on free video memory: {free / 1024:.1f} GB free now, about {need_gb:.0f} GB "
                                "needed. Close other GPU apps first."], None
        return "fits", [], None
    if variant.accelerator in {"mps", "mlx"}:
        if not facts.get("apple_silicon"):
            return "unavailable", ["Needs a Mac with Apple Silicon."], None
        return "fits", [], None
    return "fits", [], None


def bundle_verdict(bundle: Bundle, catalog: Catalog, facts: Mapping[str, Any], installed: Installed,
                   runtime_bytes: Callable[[str], int]) -> Verdict:
    platform = str(facts.get("platform") or "")
    verdict = Verdict(bundle=bundle.id, label=bundle.label, description=bundle.description,
                      capability=bundle.capability, status="fits")
    variant = bundle.variant(platform)
    if variant is None:
        names = {"windows-x64": "Windows", "macos-arm64": "macOS", "macos-x64": "macOS on Intel", "linux-x64": "Linux"}
        verdict.status = "unavailable"
        verdict.reasons = [f"Not available on {names.get(platform, platform)}."]
        return verdict
    verdict.note = variant.note
    closure = catalog.runtime_closure(variant.runtimes)
    verdict.models = list(variant.models)
    verdict.runtimes = [pack.id for pack in closure]
    canonical = [catalog.canonical_id(model_id) for model_id in variant.models]
    verdict.installed = (all(model_id in installed.models for model_id in canonical)
                         and all(pack.id in installed.runtimes for pack in closure))
    verdict.model_bytes = sum(catalog.model(model_id).size for model_id in canonical if model_id not in installed.models)
    verdict.runtime_bytes = sum(runtime_bytes(pack.id) for pack in closure if pack.id not in installed.runtimes)
    status, reasons, action = _gpu_reasons(variant, closure, facts)
    verdict.status, verdict.reasons, verdict.action = status, list(reasons), action
    if status != "unavailable":
        memory = facts.get("memory") or {}
        commit = memory.get("commit_available_bytes")
        if variant.min_commit_mb is not None and commit is not None and commit < variant.min_commit_mb * 2**20:
            verdict.status = "warn"
            verdict.reasons.append(f"Low on memory: {commit / 2**30:.1f} GB of commit left, about "
                                   f"{variant.min_commit_mb / 1024:.0f} GB needed to load it.")
        if variant.min_vram_mb is None and variant.accelerator == "cuda":
            verdict.reasons.append("Its memory needs have not been measured yet.")
            verdict.status = "warn" if verdict.status == "fits" else verdict.status
        free = (facts.get("disk") or {}).get("free_bytes")
        needed = verdict.model_bytes + int(verdict.runtime_bytes * RUNTIME_DISK_FACTOR)
        if free is not None and not verdict.installed and needed > free:
            verdict.status = "unavailable"
            verdict.reasons.append(f"Not enough disk space: about {needed / 1e9:.1f} GB needed, "
                                   f"{free / 1e9:.1f} GB free.")
    return verdict


def verdicts(catalog: Catalog, facts: Mapping[str, Any], installed: Installed,
             runtime_bytes: Callable[[str], int]) -> list[Verdict]:
    """Every bundle, in the order the setup screen lists them; ``recommended`` marks the Recommended preset."""
    found = [bundle_verdict(bundle, catalog, facts, installed, runtime_bytes)
             for bundle in sorted(catalog.bundles.values(), key=lambda item: (item.recommended_rank, item.id))]
    for verdict in found:
        verdict.recommended = verdict.status == "fits" and not verdict.installed
    return found


def selection_size(catalog: Catalog, bundles: Iterable[str], platform: str, installed: Installed,
                   runtime_bytes: Callable[[str], int]) -> dict[str, int]:
    """The download a selection of bundles needs, counting each runtime and model once."""
    models: set[str] = set()
    runtimes: set[str] = set()
    for bundle_id in bundles:
        variant = catalog.bundle(bundle_id).variant(platform)
        if variant is None:
            continue
        models.update(catalog.canonical_id(model_id) for model_id in variant.models)
        runtimes.update(pack.id for pack in catalog.runtime_closure(variant.runtimes))
    model_bytes = sum(catalog.model(model_id).size for model_id in models - installed.models)
    runtime_total = sum(runtime_bytes(runtime_id) for runtime_id in runtimes - installed.runtimes)
    return {"model_bytes": model_bytes, "runtime_bytes": runtime_total, "total_bytes": model_bytes + runtime_total}


__all__ = ["Installed", "NVIDIA_DRIVERS", "Verdict", "bundle_verdict", "selection_size", "verdicts"]
