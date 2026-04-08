"""Phase 12.12 — Local SD / ComfyUI image provider."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict

from .base import BaseImageProvider, ImageGenerationResult

_DEFAULT_COMFY_BASE_URL = "http://127.0.0.1:8188"
_DEFAULT_TIMEOUT_SEC = 180
_DEFAULT_POLL_INTERVAL_SEC = 1.0
_DEFAULT_MAX_POLLS = 120


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
    return " ".join(parts).strip()


def _build_prompt(prompt: str, *, kind: str, style: str, target_id: str) -> str:
    prompt = _safe_str(prompt).strip()
    target_id = _safe_str(target_id).strip()
    suffix = _style_hint(kind, style)
    parts = [part for part in [prompt, suffix, f"Target ID: {target_id}." if target_id else ""] if part]
    return "\n\n".join(parts).strip()


def _json_request(url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, timeout: int) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_bytes(url: str, timeout: int) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def _default_prompt_graph(prompt: str, *, seed: int, width: int, height: int) -> Dict[str, Any]:
    """Simple ComfyUI API-format graph.

    This assumes a common node layout. If the user maintains a custom workflow,
    they can override via COMFY_PROMPT_GRAPH_JSON.
    """
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 24,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": os.getenv("COMFY_CHECKPOINT_NAME", "v1-5-pruned-emaonly.safetensors"),
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt,
                "clip": ["4", 1],
            },
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "blurry, distorted, malformed hands, extra limbs, unreadable face, cropped",
                "clip": ["4", 1],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "rpg",
                "images": ["8", 0],
            },
        },
    }


class ComfyImageProvider(BaseImageProvider):
    """Local ComfyUI-backed image provider."""
    provider_name = "comfy"

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
        base_url = _safe_str(os.getenv("COMFY_BASE_URL", _DEFAULT_COMFY_BASE_URL)).strip().rstrip("/")
        timeout = _safe_int(os.getenv("COMFY_TIMEOUT_SEC"), _DEFAULT_TIMEOUT_SEC)
        poll_interval = float(os.getenv("COMFY_POLL_INTERVAL_SEC", str(_DEFAULT_POLL_INTERVAL_SEC)))
        max_polls = _safe_int(os.getenv("COMFY_MAX_POLLS"), _DEFAULT_MAX_POLLS)

        width = 768 if _safe_str(kind).strip() == "character_portrait" else 1024
        height = 1024 if _safe_str(kind).strip() == "character_portrait" else 768
        final_prompt = _build_prompt(prompt, kind=kind, style=style, target_id=target_id)
        final_seed = seed if isinstance(seed, int) else 0

        graph_override = _safe_str(os.getenv("COMFY_PROMPT_GRAPH_JSON")).strip()
        if graph_override:
            try:
                workflow = json.loads(graph_override)
            except Exception:
                return ImageGenerationResult(
                    ok=False,
                    status="failed",
                    error="comfy_invalid_prompt_graph_json",
                    moderation_status="approved",
                    moderation_reason="",
                )
        else:
            workflow = _default_prompt_graph(final_prompt, seed=final_seed, width=width, height=height)

        try:
            queued = _json_request(
                f"{base_url}/prompt",
                {"prompt": workflow},
                timeout=timeout,
            )
        except urllib.error.URLError:
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="comfy_network_error",
                moderation_status="approved",
                moderation_reason="",
            )
        except Exception:
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="comfy_submit_failed",
                moderation_status="approved",
                moderation_reason="",
            )

        prompt_id = _safe_str(queued.get("prompt_id")).strip()
        if not prompt_id:
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="comfy_missing_prompt_id",
                moderation_status="approved",
                moderation_reason="",
            )

        for _ in range(max_polls):
            try:
                history = _get_json(f"{base_url}/history/{prompt_id}", timeout=timeout)
            except urllib.error.URLError:
                return ImageGenerationResult(
                    ok=False,
                    status="failed",
                    error="comfy_history_network_error",
                    moderation_status="approved",
                    moderation_reason="",
                )
            except Exception:
                history = {}

            prompt_history = _safe_dict(history.get(prompt_id))
            outputs = _safe_dict(prompt_history.get("outputs"))
            for node_output in outputs.values():
                node_output = _safe_dict(node_output)
                images = node_output.get("images")
                if isinstance(images, list) and images:
                    image0 = _safe_dict(images[0])
                    filename = _safe_str(image0.get("filename")).strip()
                    subfolder = _safe_str(image0.get("subfolder")).strip()
                    img_type = _safe_str(image0.get("type")).strip() or "output"
                    if filename:
                        try:
                            query = f"filename={filename}&subfolder={subfolder}&type={img_type}"
                            image_bytes = _get_bytes(f"{base_url}/view?{query}", timeout=timeout)
                        except urllib.error.URLError:
                            return ImageGenerationResult(
                                ok=False,
                                status="failed",
                                error="comfy_image_fetch_network_error",
                                moderation_status="approved",
                                moderation_reason="",
                            )
                        except Exception:
                            return ImageGenerationResult(
                                ok=False,
                                status="failed",
                                error="comfy_image_fetch_failed",
                                moderation_status="approved",
                                moderation_reason="",
                            )

                        return ImageGenerationResult(
                            ok=True,
                            status="complete",
                            image_bytes=image_bytes,
                            mime_type="image/png",
                            revised_prompt=final_prompt,
                            moderation_status="approved",
                            moderation_reason="",
                        )

            time.sleep(poll_interval)

        return ImageGenerationResult(
            ok=False,
            status="failed",
            error="comfy_timeout",
            moderation_status="approved",
            moderation_reason="",
        )