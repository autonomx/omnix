"""FLUX.2 Klein image provider."""
from __future__ import annotations

import contextlib
import gc
import inspect
import os
import threading
import time
from typing import Any, Dict

import torch

from app.image.downloads import get_flux_local_model_status
from app.image.flux_pipeline_compat import (
    build_flux_pipeline,
    validate_flux_pipeline_import,
    validate_flux_repo_runtime,
)
from app.image.providers.base import BaseImageProvider, ImageGenerationResult
from app.runtime_paths import generated_images_root

_PIPELINE_LOCK = threading.Lock()
_GENERATE_LOCK = threading.Lock()
_GIB = float(1024**3)
_DEFAULT_MIN_LOAD_FREE_GIB = 14.0
_DEFAULT_MIN_GENERATION_FREE_GIB = 3.0
_DEFAULT_MAX_PIXELS = 1024 * 1024


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = _safe_str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _cuda_memory_gib() -> tuple[float, float] | None:
    if not torch.cuda.is_available():
        return None
    try:
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        return free_bytes / _GIB, total_bytes / _GIB
    except Exception:
        return None


def _release_generation_memory() -> None:
    """Release transient CPU/GPU allocations before another request can start."""

    with contextlib.suppress(Exception):
        gc.collect()
    with contextlib.suppress(Exception):
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()


class FluxKleinImageProvider(BaseImageProvider):
    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__(config)
        self._pipeline = None
        self._memory_mode = "unloaded"
        self._warmed_up = False
        self._warmup_state = "not_started"
        self._warmup_error = ""
        self._warmup_duration_ms: int | None = None

    def load(self):
        self._ensure_pipeline()
        return None

    def is_loaded(self) -> bool:
        with _PIPELINE_LOCK:
            return self._pipeline is not None

    def runtime_status(self) -> Dict[str, Any]:
        memory = _cuda_memory_gib()
        return {
            "memory_mode": self._memory_mode,
            "cuda_available": torch.cuda.is_available(),
            "cuda_free_gib": round(memory[0], 2) if memory else None,
            "cuda_total_gib": round(memory[1], 2) if memory else None,
            "warmed_up": self._warmed_up,
            "warmup_state": self._warmup_state,
            "warmup_error": self._warmup_error,
            "warmup_duration_ms": self._warmup_duration_ms,
        }

    def _repo_id(self) -> str:
        variant = _safe_str(self.config.get("variant")).strip().lower()
        if variant == "base":
            return _safe_str(self.config.get("base_repo_id")).strip() or "black-forest-labs/FLUX.2-klein-base-4B"
        return _safe_str(self.config.get("repo_id")).strip() or "black-forest-labs/FLUX.2-klein-4B"

    def _local_dir(self) -> str:
        local_dir = _safe_str(self.config.get("local_dir")).strip()
        if local_dir:
            return os.path.normpath(local_dir)

        download_dir = _safe_str(self.config.get("download_dir")).strip() or "image"
        if os.path.isabs(download_dir):
            root = download_dir
        else:
            from app.shared import MODELS_DIR

            root = os.path.join(MODELS_DIR, download_dir)

        preferred = os.path.normpath(os.path.join(root, "flux2-klein-4b"))
        legacy = os.path.normpath(os.path.join(root, "flux-klein"))

        if os.path.isdir(preferred):
            return preferred
        if os.path.isdir(legacy):
            return legacy
        return preferred

    def _dtype(self):
        dtype_name = _safe_str(self.config.get("torch_dtype")).strip().lower()
        if dtype_name == "float16":
            return torch.float16
        if dtype_name == "float32":
            return torch.float32
        return torch.bfloat16

    def _resolve_memory_mode(self) -> str:
        device = _safe_str(self.config.get("device")).strip().lower() or "cuda"
        if device != "cuda":
            return "cpu"
        if not torch.cuda.is_available():
            raise RuntimeError("flux_klein_cuda_unavailable")

        explicit_offload = _optional_bool(self.config.get("enable_cpu_offload"))
        memory = _cuda_memory_gib()
        free_gib = memory[0] if memory else None
        total_gib = memory[1] if memory else None

        if explicit_offload is True:
            return "cpu_offload"
        if explicit_offload is None and total_gib is not None and total_gib < 16.0:
            return "cpu_offload"

        min_free_gib = _safe_float(
            self.config.get("min_cuda_free_gib"),
            _DEFAULT_MIN_LOAD_FREE_GIB,
        )
        if free_gib is not None and free_gib < min_free_gib:
            raise RuntimeError(
                "flux_klein_insufficient_vram:"
                f"free_gib={free_gib:.2f} required_gib={min_free_gib:.2f} "
                f"total_gib={total_gib:.2f}; unload other GPU models before loading FLUX"
            )
        return "cuda_direct"

    def _generation_budget_error(self, width: int, height: int) -> str:
        max_pixels = _safe_int(self.config.get("max_pixels"), _DEFAULT_MAX_PIXELS)
        pixels = max(1, width * height)
        if pixels > max_pixels:
            return (
                "flux_klein_image_too_large:"
                f"requested_pixels={pixels} max_pixels={max_pixels} "
                f"requested_size={width}x{height}"
            )

        if self._memory_mode != "cuda_direct":
            return ""
        memory = _cuda_memory_gib()
        if memory is None:
            return ""
        free_gib, total_gib = memory
        configured_min = _safe_float(
            self.config.get("min_generation_free_gib"),
            _DEFAULT_MIN_GENERATION_FREE_GIB,
        )
        scaled_min = 4.0 * (pixels / _DEFAULT_MAX_PIXELS)
        required_gib = max(configured_min, scaled_min)
        if free_gib < required_gib:
            return (
                "flux_klein_insufficient_generation_vram:"
                f"free_gib={free_gib:.2f} required_gib={required_gib:.2f} "
                f"total_gib={total_gib:.2f} requested_size={width}x{height}; "
                "unload other GPU models or reduce image size"
            )
        return ""

    def _ensure_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline

        with _PIPELINE_LOCK:
            if self._pipeline is not None:
                return self._pipeline

            compat = validate_flux_pipeline_import()
            if not compat.get("ok"):
                raise RuntimeError(f"flux_klein_missing_runtime:{compat.get('error')}")

            pipeline_name = (compat.get("details") or {}).get("pipeline_class", "unknown")
            print(f"[FLUX] Using pipeline: {pipeline_name}")

            local_dir = self._local_dir()
            prefer_local = bool(self.config.get("prefer_local_files", True))
            allow_repo_fallback = bool(self.config.get("allow_repo_fallback", False))

            local_status = get_flux_local_model_status(local_dir)
            if local_status.get("complete"):
                repo_or_path = local_dir
                repo_compat = validate_flux_repo_runtime(repo_or_path)
                if not repo_compat.get("ok"):
                    raise RuntimeError(
                        "flux_klein_missing_runtime:"
                        + _safe_str(repo_compat.get("error")).strip()
                    )
                local_files_only = bool(prefer_local)
            else:
                if not allow_repo_fallback:
                    missing = ",".join(local_status.get("missing") or [])
                    raise RuntimeError(
                        "flux_klein_local_model_missing:"
                        f"{local_dir}"
                        f" missing={missing} "
                        "download first via /api/image/models/flux-klein/download"
                    )
                repo_or_path = self._repo_id()
                local_files_only = False

            memory_mode = self._resolve_memory_mode()
            memory = _cuda_memory_gib()
            memory_text = (
                f" free={memory[0]:.2f}GiB total={memory[1]:.2f}GiB"
                if memory
                else ""
            )
            print(f"[FLUX] Memory mode: {memory_mode}{memory_text}")

            pipe = build_flux_pipeline(
                repo_or_path,
                torch_dtype=self._dtype(),
                local_files_only=local_files_only,
                device_map="cuda" if memory_mode == "cuda_direct" else None,
            )

            if memory_mode == "cpu_offload":
                pipe.enable_model_cpu_offload()

            self._memory_mode = memory_mode
            self._pipeline = pipe
            return self._pipeline

    def warmup(self, *, force: bool = False) -> Dict[str, Any]:
        """Run a representative inference pass without writing an image asset."""

        if self._warmed_up and not force:
            return {
                "ok": True,
                "warmed_up": True,
                "skipped": True,
                "state": self._warmup_state,
                "duration_ms": self._warmup_duration_ms,
            }

        width = max(128, _safe_int(self.config.get("warmup_width"), 768))
        height = max(128, _safe_int(self.config.get("warmup_height"), 768))
        steps = max(1, _safe_int(self.config.get("warmup_steps"), 4))
        guidance_scale = _safe_float(self.config.get("warmup_guidance_scale"), 1.0)
        started = time.perf_counter()

        with _GENERATE_LOCK:
            output = None
            pipe = None
            self._warmed_up = False
            self._warmup_state = "running"
            self._warmup_error = ""
            try:
                pipe = self._ensure_pipeline()
                budget_error = self._generation_budget_error(width, height)
                if budget_error:
                    raise RuntimeError(budget_error)
                kwargs: Dict[str, Any] = {
                    "prompt": "simple warmup image, single softly glowing lantern, no text",
                    "negative_prompt": "text, watermark, logo",
                    "width": width,
                    "height": height,
                    "num_inference_steps": steps,
                    "guidance_scale": guidance_scale,
                    "generator": torch.Generator(device="cpu").manual_seed(1),
                }
                with torch.inference_mode():
                    output = pipe(**kwargs)
                    images = getattr(output, "images", None)
                    if images:
                        _ = images[0]
                with contextlib.suppress(Exception):
                    if torch.cuda.is_available():
                        torch.cuda.synchronize()
                self._warmup_duration_ms = round((time.perf_counter() - started) * 1000)
                self._warmed_up = True
                self._warmup_state = "completed"
                return {
                    "ok": True,
                    "warmed_up": True,
                    "skipped": False,
                    "state": self._warmup_state,
                    "duration_ms": self._warmup_duration_ms,
                    "width": width,
                    "height": height,
                    "steps": steps,
                }
            except Exception as exc:
                self._warmup_duration_ms = round((time.perf_counter() - started) * 1000)
                self._warmup_error = _safe_str(exc).strip() or repr(exc)
                self._warmup_state = "failed"
                return {
                    "ok": False,
                    "warmed_up": False,
                    "skipped": False,
                    "state": self._warmup_state,
                    "duration_ms": self._warmup_duration_ms,
                    "error": self._warmup_error,
                }
            finally:
                output = None
                pipe = None
                _release_generation_memory()

    def unload(self):
        with _GENERATE_LOCK:
            with _PIPELINE_LOCK:
                pipe = self._pipeline
                self._pipeline = None
                self._memory_mode = "unloaded"
                self._warmed_up = False
                self._warmup_state = "not_started"
                self._warmup_error = ""
                self._warmup_duration_ms = None

            with contextlib.suppress(Exception):
                del pipe

            _release_generation_memory()

        return None

    def generate(self, payload: Dict[str, Any]) -> ImageGenerationResult:
        prompt = _safe_str(payload.get("prompt")).strip()
        negative_prompt = _safe_str(payload.get("negative_prompt")).strip()
        width = _safe_int(payload.get("width"), _safe_int(self.config.get("width"), 768))
        height = _safe_int(payload.get("height"), _safe_int(self.config.get("height"), 768))
        seed = payload.get("seed")
        steps = _safe_int(
            payload.get("num_inference_steps"),
            _safe_int(self.config.get("num_inference_steps"), 4),
        )
        guidance_scale = _safe_float(
            payload.get("guidance_scale"),
            _safe_float(self.config.get("guidance_scale"), 1.0),
        )

        kwargs: Dict[str, Any] = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_inference_steps": steps,
            "guidance_scale": guidance_scale,
        }
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        if seed is not None:
            with contextlib.suppress(Exception):
                kwargs["generator"] = torch.Generator(device="cpu").manual_seed(int(seed))

        progress_callback = payload.get("_progress_callback")

        def report_progress(current: int) -> None:
            if callable(progress_callback):
                with contextlib.suppress(Exception):
                    progress_callback(
                        max(0, min(steps, current)),
                        max(1, steps),
                        "Generating image",
                    )

        with _GENERATE_LOCK:
            pipe = None
            output = None
            image = None
            try:
                try:
                    pipe = self._ensure_pipeline()
                except Exception as exc:
                    return ImageGenerationResult(
                        ok=False,
                        status="failed",
                        error=_safe_str(exc).strip() or f"flux_klein_load_failed:{repr(exc)}",
                        moderation_status="approved",
                        moderation_reason="",
                    )

                budget_error = self._generation_budget_error(width, height)
                if budget_error:
                    return ImageGenerationResult(
                        ok=False,
                        status="failed",
                        error=budget_error,
                        moderation_status="approved",
                        moderation_reason="",
                    )

                try:
                    report_progress(0)
                    with contextlib.suppress(Exception):
                        signature = inspect.signature(pipe.__call__)
                        params = signature.parameters
                        if "callback_on_step_end" in params:

                            def on_step_end(
                                _pipeline,
                                step: int,
                                _timestep,
                                callback_kwargs: Dict[str, Any],
                            ):
                                report_progress(int(step) + 1)
                                return callback_kwargs

                            kwargs["callback_on_step_end"] = on_step_end
                            if "callback_on_step_end_tensor_inputs" in params:
                                kwargs["callback_on_step_end_tensor_inputs"] = []
                        elif "callback" in params:

                            def on_step(step: int, _timestep, _latents):
                                report_progress(int(step) + 1)

                            kwargs["callback"] = on_step
                            if "callback_steps" in params:
                                kwargs["callback_steps"] = 1

                    with torch.inference_mode():
                        output = pipe(**kwargs)
                        image = output.images[0]
                    report_progress(steps)
                except Exception as exc:
                    return ImageGenerationResult(
                        ok=False,
                        status="failed",
                        error=f"flux_klein_generate_failed:{repr(exc)}",
                        moderation_status="approved",
                        moderation_reason="",
                    )

                out_dir = str(generated_images_root())
                os.makedirs(out_dir, exist_ok=True)
                filename = (
                    f"{_safe_str(payload.get('kind')).strip() or 'image'}_"
                    f"{os.getpid()}_{id(image)}.png"
                )
                file_path = os.path.normpath(os.path.join(out_dir, filename))

                try:
                    image.save(file_path, format="PNG")
                except Exception as exc:
                    with contextlib.suppress(OSError):
                        os.remove(file_path)
                    return ImageGenerationResult(
                        ok=False,
                        status="failed",
                        error=f"flux_klein_finalize_failed:{repr(exc)}",
                        moderation_status="approved",
                        moderation_reason="",
                    )

                return ImageGenerationResult(
                    ok=True,
                    status="completed",
                    error="",
                    moderation_status="approved",
                    moderation_reason="",
                    mime_type="image/png",
                    revised_prompt=prompt,
                    file_path=file_path,
                    asset_url="",
                    metadata={
                        "width": width,
                        "height": height,
                        "memory_mode": self._memory_mode,
                    },
                )
            finally:
                output = None
                image = None
                pipe = None
                _release_generation_memory()
