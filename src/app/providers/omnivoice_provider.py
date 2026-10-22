"""OmniVoice TTS provider (Voice Studio Phase 5).

OmniVoice (k2-fsa) speaks 600+ languages and clones a voice from a few seconds
of reference audio. Its weights are CC-BY-NC-4.0 (training-data terms), so the
Models tool installs them only after the terms are accepted.

It runs in its own environment (``src/services/omnivoice``) as a child server
of the process that owns TTS (``ManagedChildServer``): ``start`` launches the
server and waits for the model, ``stop`` ends it and frees the GPU, so the
engine picker and the swap controller treat it like any other engine.

Voices come from the shared Voice Library: each request sends the sample and
its transcript, and the server caches the encoded reference. Without a voice
sample it uses OmniVoice's automatic voice.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import sys
import threading
import wave
from pathlib import Path
from typing import Any, Optional

from app.runtime.paths import repo_root, resources_models_root, writable_resources_root

from .audio_base import AudioProviderCapability, BaseTTSProvider
from .child_model_server import ManagedChildServer
from .tts_priority import generation_slot
from .voice_references import clone_reference, clone_speakers

logger = logging.getLogger(__name__)

PROVIDER_ID = "omnivoice"
MODEL_DIR_NAME = "OmniVoice"
SAMPLE_RATE = 24_000
DEFAULT_OMNIVOICE_SETTINGS: dict[str, Any] = {
    "port": 5103,
    "model_dir": "",
    "python": "",
    "startup_timeout_s": 600,
    # Diffusion steps: 32 is the published default, 16 is faster with a small quality cost.
    "num_step": 32,
}
_GENERATION_KEYS = ("num_step", "guidance_scale", "class_temperature", "speed", "duration", "seed")


def model_dir(config: Optional[dict[str, Any]] = None) -> Path:
    from app.models.local import installed_snapshot

    # The desktop app installs the catalog's pinned weights; a folder named in settings does not apply there.
    snapshot = installed_snapshot("omnivoice")
    if snapshot is not None:
        return snapshot
    configured = str((config or {}).get("model_dir") or "").strip()
    return Path(configured) if configured else resources_models_root() / "tts" / MODEL_DIR_NAME


def _desktop_site_dirs() -> list[Path] | None:
    """The desktop app's OmniVoice overlay and the Torch layer under it (overlay first); None outside the app."""
    from app.models import catalog as model_catalog
    from app.models import packs

    if not packs.desktop_mode():
        return None
    catalog = model_catalog.load()
    store = packs.runtime_store(catalog)
    platform = model_catalog.current_platform()
    for bundle in catalog.bundles.values():
        variant = bundle.variant(platform)
        option = variant.option("omnivoice") if variant is not None else None
        if option is not None and option.runtimes:
            closure = catalog.runtime_closure(option.runtimes)
            return [store.site(pack.id) for pack in reversed(closure)]
    raise RuntimeError("OmniVoice has no runtime on this platform")


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _python(configured: str) -> str:
    if configured:
        return configured
    from app.config.launcher import load_launcher_config

    return load_launcher_config(repo_root()).python("omnivoice")


def _wav_reference(path: str) -> bytes:
    import soundfile

    audio, rate = soundfile.read(path, dtype="float32", always_2d=False)
    if getattr(audio, "ndim", 1) > 1:
        audio = audio.mean(axis=1)
    buffer = io.BytesIO()
    soundfile.write(buffer, audio, rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


class OmniVoiceTTSProvider(BaseTTSProvider):
    provider_name = PROVIDER_ID
    provider_display_name = "OmniVoice"
    provider_description = "Zero-shot voice cloning in 600+ languages (k2-fsa OmniVoice, non-commercial weights)"
    generation_strategy_revision = "omnivoice-generation-v1"
    sample_rate = SAMPLE_RATE
    default_capabilities = [AudioProviderCapability.VOICE_CLONING, AudioProviderCapability.MULTILINGUAL]

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__({**DEFAULT_OMNIVOICE_SETTINGS, **dict(config or {})})
        self._lock = threading.Lock()
        self._last_error = ""
        logs = writable_resources_root() / "logs" / "tts"
        self.server = ManagedChildServer(
            label="OmniVoice", port=int(self.config["port"]), command=self._server_command,
            cwd=repo_root(), log_path=logs / "omnivoice.log", pid_path=logs / "omnivoice.pid",
            startup_timeout_s=float(self.config["startup_timeout_s"]),
            environment=self._child_environment,
        )

    @staticmethod
    def local_model_artifacts():
        from app.settings.access import load_settings

        from .tts_artifacts import LocalArtifactsUnavailable, LocalModelArtifacts

        directory = model_dir(load_settings().get(PROVIDER_ID) or {}).resolve()
        if not directory.is_dir() or not list(directory.glob("*.safetensors")):
            raise LocalArtifactsUnavailable("install OmniVoice from Voice Studio's Models tool (accept its terms first)")
        return LocalModelArtifacts(model_id="OmniVoice", directory=directory)

    def _server_command(self) -> list[str]:
        arguments = ["--model-dir", str(model_dir(self.config).resolve()), "--port", str(int(self.server.port))]
        if _desktop_site_dirs() is not None:
            # The desktop app: the bundled interpreter with the OmniVoice overlay only (``service_boot`` -S).
            return [sys.executable, "-S", "-m", "app.desktop.service_boot", "omnivoice", *arguments]
        server = Path(__file__).resolve().parents[2] / "services" / "omnivoice" / "omnivoice_server.py"
        return [_python(str(self.config.get("python") or "").strip()), str(server), *arguments]

    @staticmethod
    def _child_environment() -> dict[str, str]:
        sites = _desktop_site_dirs()
        if sites is None:
            return {}
        from app.config.env import environment

        source = environment()
        env = {"OMNIX_DESKTOP_SITE_DIRS": os.pathsep.join(str(site) for site in sites)}
        if source.get("PYTHONPATH"):
            env["PYTHONPATH"] = source["PYTHONPATH"]  # a development interpreter finds the app source this way
        return env

    # -- lifecycle --------------------------------------------------------

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.server.process is not None and self.server.process.poll() is None and self.server.healthy():
                return {"running": True, "message": f"OmniVoice is serving at {self.server.base_url}"}
            try:
                if not list(model_dir(self.config).glob("*.safetensors")):
                    raise RuntimeError(f"OmniVoice weights are missing from {model_dir(self.config)}")
                if _desktop_site_dirs() is not None:
                    # Never a developer Omnix's port (5103): a free one for this start.
                    self.server.port = _free_port()
                self.server.launch_and_wait()
            except Exception as exc:
                self._last_error = str(exc)
                logger.error("OmniVoice failed to start: %s", exc)
                self.server.terminate()
                return {"running": False, "message": f"Failed to start: {exc}", "error": str(exc),
                        "provider_state": self.get_runtime_status()}
            self._last_error = ""
            return {"running": True, "message": f"OmniVoice loaded from {model_dir(self.config)}"}

    def stop(self) -> bool:
        """End the OmniVoice server: the process exit releases its GPU memory."""
        with self._lock:
            try:
                self.server.terminate()
            except Exception as exc:
                logger.error("Error stopping OmniVoice: %s", exc)
                return False
            self.server.close()
            return True

    def health_check(self) -> bool:
        return self.server.healthy()

    def test_connection(self) -> bool:
        return self.health_check()

    def get_runtime_status(self) -> dict[str, Any]:
        process = self.server.process
        return {"model_loaded": self.server.healthy(), "server_url": self.server.base_url,
                "server_pid": process.pid if process is not None and process.poll() is None else None,
                "configured_model_source": str(model_dir(self.config)), "last_error": self._last_error}

    def get_capabilities(self) -> list[AudioProviderCapability]:
        return self.default_capabilities.copy()

    def supports_streaming(self) -> bool:
        return False

    def supports_voice_cloning(self) -> bool:
        return True

    # -- synthesis --------------------------------------------------------

    def get_speakers(self) -> list[dict[str, Any]]:
        return clone_speakers()

    def resolve_generation_parameters(self, parameters: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        requested = dict(parameters or {})
        resolved = {key: requested.get(key, self.config.get(key)) for key in _GENERATION_KEYS}
        resolved["_generation_strategy_revision"] = self.generation_strategy_revision
        return resolved

    def _request(self, text: str, speaker: Optional[str], parameters: dict[str, Any],
                 language: Optional[str] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"text": text, "num_step": int(parameters.get("num_step") or 32)}
        for key in ("guidance_scale", "class_temperature"):
            if parameters.get(key) is not None:
                payload[key] = float(parameters[key])
        if parameters.get("duration"):
            payload["duration"] = float(parameters["duration"])
        elif parameters.get("speed"):
            payload["speed"] = float(parameters["speed"])
        if parameters.get("seed") is not None:
            payload["seed"] = int(parameters["seed"])
        if language:
            payload["language"] = str(language).split("-")[0].split("_")[0].lower()
        path, transcript = clone_reference(speaker) if speaker and speaker != "default" else (None, "")
        if path:
            if not transcript:
                from app.assets.voice_clone_identity import reference_transcript

                transcript = reference_transcript(path)
            if not transcript and _desktop_site_dirs() is not None:
                # Without one OmniVoice would fetch Whisper to transcribe the sample, and the desktop app is offline.
                raise RuntimeError(f"OmniVoice needs a transcript of the {speaker} voice sample: download Speech input "
                                   "in Settings, Models, then choose OmniVoice again so Omnix can transcribe it")
            payload.update(ref_audio=base64.b64encode(_wav_reference(path)).decode("ascii"), ref_text=transcript)
        return payload

    def generate_audio(self, text: str, speaker: Optional[str] = None, language: Optional[str] = None,
                       **kwargs: Any) -> dict[str, Any]:
        """Speak ``text`` in the speaker's library voice (or OmniVoice's automatic voice)."""
        kwargs.pop("_progress_callback", None)
        kwargs.pop("instruct", None)  # delivery notes are not speaker attributes; OmniVoice would misread them
        parameters = self.resolve_generation_parameters(kwargs)
        try:
            payload = self._request(text, speaker, parameters, language)
            with generation_slot():
                response = self.server.http().post(self.server.base_url + "/generate", json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"OmniVoice server returned {response.status_code}: {response.text[:300]}")
            wav_bytes = response.content
            with wave.open(io.BytesIO(wav_bytes), "rb") as clip:
                rate, frames = clip.getframerate(), clip.getnframes()
        except Exception as exc:
            logger.error("OmniVoice generation failed: %s", exc)
            return {"success": False, "error": str(exc), "provider": PROVIDER_ID}
        encoded = base64.b64encode(wav_bytes).decode("ascii")
        return {"success": True, "audio": encoded, "audio_base64": encoded, "sample_rate": rate,
                "duration": frames / rate if rate else 0.0, "format": "audio/wav", "provider": PROVIDER_ID,
                "generation_parameters_used": parameters,
                "generation_strategy_revision": self.generation_strategy_revision}

    def generate_audio_with_progress(self, text: str, speaker: Optional[str] = None,
                                     language: Optional[str] = None, *, progress_callback=None, **kwargs):
        return self.generate_audio(text, speaker=speaker, language=language, **kwargs)

    def generate_audio_stream(self, *args: Any, **kwargs: Any):
        raise NotImplementedError("OmniVoice renders whole utterances; it does not stream")

    def voice_clone(self, voice_id: str, audio_data: bytes, ref_text: Optional[str] = None) -> dict[str, Any]:
        """Clones live in the shared Voice Library; there is nothing engine-side to register."""
        return {"success": True, "voice_id": voice_id, "provider": PROVIDER_ID}


__all__ = ["DEFAULT_OMNIVOICE_SETTINGS", "OmniVoiceTTSProvider", "PROVIDER_ID", "model_dir"]
