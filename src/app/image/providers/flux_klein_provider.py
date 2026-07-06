"""FLUX.2 Klein image provider."""
from __future__ import annotations

import contextlib
import gc
import inspect
import os
import threading
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

    def load(self):
        self._ensure_pipeline()
        return None

    def is_loaded(self) -> bool:
        with _PIPELINE_LOCK:
            return self._pipeline is not None

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
        import torch

        dtype_name = _safe_str(self.config.get("torch_dtype")).strip().lower()
        if dtype_name == "float16":
            return torch.float16
        if dtype_name == "float32":
            return torch.float32
        return torch.bfloat16

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

            pipe = build_flux_pipeline(
                repo_or_path,
                torch_dtype=self._dtype(),
                local_files_only=local_files_only,
            )

            enable_cpu_offload = bool(self.config.get("enable_cpu_offload", True))
            device = _safe_str(self.config.get("device")).strip().lower() or "cuda"

            if enable_cpu_offload:
                with contextlib.suppress(Exception):
                    pipe.enable_model_cpu_offload()
            elif device == "cuda":
                with contextlib.suppress(Exception):
                    pipe.to("cuda")

            self._pipeline = pipe
            return self._pipeline

    def unload(self):
        with _GENERATE_LOCK:
            with _PIPELINE_LOCK:
                pipe = self._pipeline
                self._pipeline = None

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
                    metadata={"width": width, "height": height},
                )
            finally:
                output = None
                image = None
                pipe = None
                _release_generation_memory()
