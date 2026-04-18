"""FLUX.2 [klein] 4B local provider with lazy load / unload."""
from __future__ import annotations

import gc
import importlib
import io
import os
import threading
from pathlib import Path
from typing import Any, Dict

from .base import BaseImageProvider, ImageGenerationResult

_PIPELINE_LOCK = threading.Lock()


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
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _style_hint(kind: str, style: str) -> str:
    kind = _safe_str(kind).strip()
    style = _safe_str(style).strip()
    parts = []
    if style:
        parts.append(f"Visual style: {style}.")
    if kind == "character_portrait":
        parts.append("Framing: character portrait, single primary subject, readable facial detail.")
    elif kind == "scene_illustration":
        parts.append("Framing: environmental scene illustration with clear composition.")
    elif kind == "item_illustration":
        parts.append("Framing: single item render on a clean readable background.")
    return " ".join(parts).strip()


def _build_prompt(prompt: str, *, kind: str, style: str, target_id: str) -> str:
    prompt = _safe_str(prompt).strip()
    suffix = _style_hint(kind, style)
    parts = [part for part in [prompt, suffix, f"Target ID: {target_id}." if target_id else ""] if part]
    return "\n\n".join(parts).strip()


class FluxKleinImageProvider(BaseImageProvider):
    provider_name = "flux_klein"

    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = _safe_dict(config)
        self._pipe = None
        self._torch = None

    def _repo_id(self) -> str:
        variant = _safe_str(self.config.get("variant")).strip().lower()
        if variant == "base":
            return _safe_str(self.config.get("base_repo_id")).strip() or "black-forest-labs/FLUX.2-klein-base-4B"
        return _safe_str(self.config.get("repo_id")).strip() or "black-forest-labs/FLUX.2-klein-4B"

    def _local_dir(self) -> str:
        local_dir = _safe_str(self.config.get("local_dir")).strip()
        return local_dir

    def _dtype(self):
        import torch

        dtype_name = _safe_str(self.config.get("torch_dtype")).strip().lower()
        if dtype_name == "float16":
            return torch.float16
        if dtype_name == "float32":
            return torch.float32
        return torch.bfloat16

    def _dimensions(self, kind: str) -> tuple[int, int]:
        kind = _safe_str(kind).strip()
        if kind == "character_portrait":
            return (
                _safe_int(self.config.get("portrait_width"), 768),
                _safe_int(self.config.get("portrait_height"), 1024),
            )
        if kind == "item_illustration":
            return (
                _safe_int(self.config.get("item_width"), 1024),
                _safe_int(self.config.get("item_height"), 1024),
            )
        return (
            _safe_int(self.config.get("scene_width"), 1024),
            _safe_int(self.config.get("scene_height"), 768),
        )

    def _ensure_pipeline(self):
        if self._pipe is not None:
            return self._pipe

        with _PIPELINE_LOCK:
            if self._pipe is not None:
                return self._pipe

            try:
                # Fix Windows multiprocessing sys.path inheritance issue
                import sys
                import os
                import site
                # Reload site packages to ensure all paths are registered
                importlib.reload(site)
                # Add parent sys.path entries that might be missing in spawned process
                for path in os.environ.get('PYTHONPATH', '').split(os.pathsep):
                    if path and path not in sys.path:
                        sys.path.insert(0, path)
                
                import torch
                from diffusers import Flux2KleinPipeline
            except Exception as exc:
                raise RuntimeError(f"flux_klein_missing_runtime:{exc}") from exc

            repo_or_path = self._repo_id()
            local_dir = self._local_dir()
            prefer_local = bool(self.config.get("prefer_local_files", True))
            if local_dir and os.path.isdir(local_dir) and any(Path(local_dir).iterdir()):
                repo_or_path = local_dir

            pipe = Flux2KleinPipeline.from_pretrained(
                repo_or_path,
                torch_dtype=self._dtype(),
                local_files_only=bool(prefer_local and local_dir and os.path.isdir(local_dir)),
            )

            device = _safe_str(self.config.get("device")).strip().lower() or "cuda"
            if bool(self.config.get("enable_cpu_offload", True)):
                pipe.enable_model_cpu_offload()
            else:
                pipe.to(device)

            self._pipe = pipe
            self._torch = torch
            return self._pipe

    def unload(self) -> None:
        with _PIPELINE_LOCK:
            pipe = self._pipe
            self._pipe = None
            self._torch = None
            if pipe is not None:
                try:
                    del pipe
                except Exception:
                    pass
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    def generate(
        self,
        *,
        prompt: str,
        seed: int | None,
        style: str,
        model: str,
        kind: str,
        target_id: str,
    ) -> ImageGenerationResult:
        try:
            pipe = self._ensure_pipeline()
        except RuntimeError as exc:
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error=str(exc),
                moderation_status="approved",
                moderation_reason="",
            )
        except Exception:
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="flux_klein_load_failed",
                moderation_status="approved",
                moderation_reason="",
            )

        final_prompt = _build_prompt(prompt, kind=kind, style=style, target_id=target_id)
        width, height = self._dimensions(kind)
        steps = _safe_int(self.config.get("num_inference_steps"), 4)
        guidance = _safe_float(self.config.get("guidance_scale"), 1.0)

        kwargs: Dict[str, Any] = {
            "prompt": final_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": steps,
            "guidance_scale": guidance,
        }

        if isinstance(seed, int) and self._torch is not None:
            generator_device = "cpu" if bool(self.config.get("enable_cpu_offload", True)) else (_safe_str(self.config.get("device")).strip().lower() or "cuda")
            kwargs["generator"] = self._torch.Generator(device=generator_device).manual_seed(seed)

        try:
            image = pipe(**kwargs).images[0]
        except Exception:
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="flux_klein_generate_failed",
                moderation_status="approved",
                moderation_reason="",
            )

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return ImageGenerationResult(
            ok=True,
            status="complete",
            image_bytes=buffer.getvalue(),
            mime_type="image/png",
            revised_prompt=final_prompt,
            moderation_status="approved",
            moderation_reason="",
        )
