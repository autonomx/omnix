"""Speech models Omnix can install, with their licences: Voice Studio's view of model catalog v2.

The models live in ``app/models/catalog.json`` (desktop roadmap §4.6), each with
its repository, pinned commit, the SHA-256 of every file a service reads, its
licence and the terms for what it generates. This module lists the ones Voice
Studio shows (``voice_studio: true``), in catalog order. Every model installs
only after its terms are accepted (roadmap D-4); the acceptance is recorded.

The environment a model runs in is not installed here: setup scripts and the
service lock files build those (``src/services/*``), or, in the desktop app,
the runtime packs. This catalog only fetches weights.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

ModelKind = Literal["tts", "stt", "audio"]
# How a model sits on the GPU (Phase 1 §6): resident engines and swapped-in
# heavy models take the TTS engine's place; small helpers may load beside it.
Residency = Literal["engine", "swap", "helper"]
# Where the weights come from: the Hugging Face hub (the install job fetches
# them), or the model's own package, which downloads them on first use.
ModelSource = Literal["huggingface", "package"]


@dataclass(frozen=True)
class SpeechModel:
    id: str
    kind: ModelKind
    label: str
    repo_id: str
    # The pinned commit for Hugging Face models; the package's own revision name otherwise.
    revision: str
    licence: str
    licence_url: str
    size_gb: float
    vram_gb: float
    residency: Residency
    # The service environment the model runs in (``src/services/<service>``).
    service: str
    commercial_use: bool = True
    gated: bool = False
    source: ModelSource = "huggingface"
    output_terms: str = ""
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    # The files the service reads (pinned, with digests in the catalog); empty for package models.
    files: tuple[str, ...] = field(default_factory=tuple)
    folder: str = ""

    @property
    def requires_acceptance(self) -> bool:
        """Every model installs only after its licence and terms are accepted (roadmap D-4)."""
        return self.source == "huggingface"

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["capabilities"] = list(self.capabilities)
        data["files"] = list(self.files)
        data["requires_acceptance"] = self.requires_acceptance
        return data


# The size Voice Studio shows for package models, which list no files.
_PACKAGE_SIZES_GB = {
    "audioseal-wm-16bits": 0.1,
    "mel-band-roformer-vocals": 0.9,
    "gtcrn-speech-enhancement": 0.01,
    "htdemucs-ft": 0.3,
}


def _speech_models() -> tuple[SpeechModel, ...]:
    from app.models.catalog import load

    models = []
    for entry in load().models.values():
        if not entry.voice_studio:
            continue
        size_gb = round(entry.size / 1e9, 2) if entry.files else _PACKAGE_SIZES_GB.get(entry.id, 0.0)
        models.append(SpeechModel(
            id=entry.id,
            kind=entry.kind,  # type: ignore[arg-type]
            label=entry.label,
            repo_id=entry.repo,
            revision=entry.revision,
            licence=entry.licence.id,
            licence_url=entry.licence.url,
            size_gb=size_gb,
            vram_gb=entry.vram_gb,
            residency=entry.residency,  # type: ignore[arg-type]
            service=entry.service,
            commercial_use=entry.licence.commercial_use,
            gated=entry.licence.gated,
            source=entry.source,  # type: ignore[arg-type]
            output_terms=entry.licence.output_terms,
            capabilities=entry.capabilities,
            files=tuple(item.path for item in entry.files),
            folder=entry.folder_name,
        ))
    return tuple(models)


SPEECH_MODELS: tuple[SpeechModel, ...] = _speech_models()

_BY_ID = {model.id: model for model in SPEECH_MODELS}


def speech_model(model_id: str) -> SpeechModel:
    try:
        return _BY_ID[model_id]
    except KeyError:
        pass
    from app.models.catalog import load

    try:
        canonical = load().canonical_id(model_id)
    except KeyError:
        raise KeyError(f"unknown speech model: {model_id}") from None
    if canonical in _BY_ID:
        return _BY_ID[canonical]
    raise KeyError(f"unknown speech model: {model_id}")


def speech_models(kind: ModelKind | None = None) -> tuple[SpeechModel, ...]:
    return tuple(model for model in SPEECH_MODELS if kind is None or model.kind == kind)
