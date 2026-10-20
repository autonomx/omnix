"""Speech models Omnix can install, with their licences (Phase 1 licence registry).

Every model a voice tool downloads is listed here with the repository and
revision it comes from, its size and VRAM estimate on the 24 GB target, its
licence, and the terms for what it generates. Install refuses a model whose
terms need acceptance (gated, or not cleared for commercial use) until the
request accepts them; the acceptance is recorded in the model's install marker.

The environment a model runs in is not installed here: setup scripts and the
service lock files build those (``src/services/*``). This catalog only fetches
weights.
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
    # File patterns to download (``allow_patterns``); empty takes the whole repository.
    # NeMo services load the ``.nemo`` archive, so other copies of the weights are skipped.
    files: tuple[str, ...] = field(default_factory=tuple)

    @property
    def requires_acceptance(self) -> bool:
        """Gated or non-commercial models install only after their terms are accepted."""
        return self.gated or not self.commercial_use

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["capabilities"] = list(self.capabilities)
        data["files"] = list(self.files)
        data["requires_acceptance"] = self.requires_acceptance
        return data


SPEECH_MODELS: tuple[SpeechModel, ...] = (
    SpeechModel(
        id="qwen3-tts-0.6b-base", kind="tts", label="Qwen3-TTS 0.6B Base",
        repo_id="Qwen/Qwen3-TTS-12Hz-0.6B-Base", revision="main",
        licence="Apache-2.0", licence_url="https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        size_gb=2.5, vram_gb=4.0, residency="engine", service="tts",
        capabilities=("synthesis", "voice_clone"),
    ),
    SpeechModel(
        # Runs in its own environment (src/services/omnivoice); the weights' training data
        # (Emilia among it) limits them to non-commercial use.
        id="omnivoice", kind="tts", label="OmniVoice (600+ languages)",
        repo_id="k2-fsa/OmniVoice", revision="main",
        licence="CC-BY-NC-4.0", licence_url="https://huggingface.co/k2-fsa/OmniVoice",
        size_gb=2.5, vram_gb=3.0, residency="engine", service="omnivoice", commercial_use=False,
        output_terms="Non-commercial use only (CC-BY-NC-4.0 weights); clone only voices you have consent for.",
        capabilities=("synthesis", "voice_clone", "many_languages"),
    ),
    SpeechModel(
        id="qwen3-tts-1.7b-voicedesign", kind="tts", label="Qwen3-TTS 1.7B VoiceDesign",
        repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", revision="main",
        licence="Apache-2.0", licence_url="https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        size_gb=4.5, vram_gb=7.0, residency="swap", service="tts",
        capabilities=("voice_design",),
    ),
    SpeechModel(
        id="parakeet-tdt-0.6b-v3", kind="stt", label="NVIDIA Parakeet-TDT 0.6B v3",
        repo_id="nvidia/parakeet-tdt-0.6b-v3", revision="main",
        licence="CC-BY-4.0", licence_url="https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3",
        size_gb=2.4, vram_gb=2.5, residency="helper", service="stt",
        output_terms="Attribution required when redistributing the model.",
        capabilities=("transcription", "word_timestamps"),
        files=("*.nemo", "README.md"),
    ),
    SpeechModel(
        id="titanet-large", kind="stt", label="NVIDIA TitaNet speaker embeddings",
        repo_id="nvidia/speakerverification_en_titanet_large", revision="main",
        licence="CC-BY-4.0", licence_url="https://huggingface.co/nvidia/speakerverification_en_titanet_large",
        size_gb=0.1, vram_gb=1.0, residency="helper", service="stt",
        output_terms="Attribution required when redistributing the model.",
        capabilities=("diarization", "speaker_embedding"),
        files=("*.nemo", "README.md"),
    ),
    SpeechModel(
        id="sortformer-4spk-v1", kind="stt", label="NVIDIA Sortformer diarizer (4 speakers)",
        repo_id="nvidia/diar_sortformer_4spk-v1", revision="main",
        licence="CC-BY-NC-4.0", licence_url="https://huggingface.co/nvidia/diar_sortformer_4spk-v1",
        size_gb=0.5, vram_gb=1.0, residency="helper", service="stt",
        commercial_use=False,
        output_terms="Non-commercial use only; opt in to use it.",
        capabilities=("diarization",),
    ),
    SpeechModel(
        id="audioseal-wm-16bits", kind="audio", label="AudioSeal watermark (16 bits)",
        repo_id="facebookresearch/audioseal", revision="audioseal_wm_16bits",
        licence="MIT", licence_url="https://github.com/facebookresearch/audioseal",
        size_gb=0.1, vram_gb=0.5, residency="helper", service="audio", source="package",
        capabilities=("watermark",),
    ),
    SpeechModel(
        # The audio service's separator fetches this checkpoint (vocals_mel_band_roformer.ckpt)
        # and its config on first use.
        id="mel-band-roformer-vocals", kind="audio", label="Mel-Band RoFormer vocal separation",
        repo_id="KimberleyJSN/melbandroformer", revision="main",
        licence="MIT", licence_url="https://huggingface.co/KimberleyJSN/melbandroformer",
        size_gb=0.9, vram_gb=2.0, residency="helper", service="audio", source="package",
        output_terms="Training data is not disclosed by the checkpoint's author.",
        capabilities=("separation",),
    ),
    SpeechModel(
        # Run by sherpa-onnx's offline denoiser; the audio service downloads it on first use.
        id="gtcrn-speech-enhancement", kind="audio", label="GTCRN speech enhancement",
        repo_id="k2-fsa/sherpa-onnx", revision="speech-enhancement-models",
        licence="MIT", licence_url="https://github.com/Xiaobin-Rong/gtcrn",
        size_gb=0.01, vram_gb=0.0, residency="helper", service="audio", source="package",
        capabilities=("enhancement",),
    ),
    SpeechModel(
        id="htdemucs-ft", kind="audio", label="Demucs v4 (fine-tuned)",
        repo_id="facebookresearch/demucs", revision="htdemucs_ft",
        licence="MIT", licence_url="https://github.com/facebookresearch/demucs",
        size_gb=0.3, vram_gb=2.0, residency="helper", service="audio", source="package",
        capabilities=("separation",),
    ),
)

_BY_ID = {model.id: model for model in SPEECH_MODELS}


def speech_model(model_id: str) -> SpeechModel:
    try:
        return _BY_ID[model_id]
    except KeyError:
        raise KeyError(f"unknown speech model: {model_id}") from None


def speech_models(kind: ModelKind | None = None) -> tuple[SpeechModel, ...]:
    return tuple(model for model in SPEECH_MODELS if kind is None or model.kind == kind)


__all__ = ["SPEECH_MODELS", "SpeechModel", "speech_model", "speech_models"]
