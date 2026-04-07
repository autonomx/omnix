"""Phase 12.11 — OpenAI image provider implementation."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict

from .base import BaseImageProvider, ImageGenerationResult


_DEFAULT_MODEL = "gpt-image-1"
_DEFAULT_SIZE = "1024x1024"
_OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


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


def _extract_result(payload: Dict[str, Any]) -> ImageGenerationResult:
    payload = _safe_dict(payload)
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return ImageGenerationResult(
            ok=False,
            status="failed",
            error="openai_no_image_data",
            moderation_status="approved",
            moderation_reason="",
        )

    first = _safe_dict(data[0])
    b64_json = _safe_str(first.get("b64_json")).strip()
    revised_prompt = _safe_str(first.get("revised_prompt")).strip()

    if not b64_json:
        return ImageGenerationResult(
            ok=False,
            status="failed",
            error="openai_missing_b64_json",
            revised_prompt=revised_prompt,
            moderation_status="approved",
            moderation_reason="",
        )

    try:
        image_bytes = base64.b64decode(b64_json)
    except Exception:
        return ImageGenerationResult(
            ok=False,
            status="failed",
            error="openai_invalid_b64_json",
            revised_prompt=revised_prompt,
            moderation_status="approved",
            moderation_reason="",
        )

    return ImageGenerationResult(
        ok=True,
        status="complete",
        image_bytes=image_bytes,
        mime_type="image/png",
        revised_prompt=revised_prompt,
        moderation_status="approved",
        moderation_reason="",
    )


class OpenAIImageProvider(BaseImageProvider):
    """OpenAI image generation provider."""
    provider_name = "openai"

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
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="openai_api_key_missing",
                moderation_status="approved",
                moderation_reason="",
            )

        model_name = _safe_str(model).strip() or _DEFAULT_MODEL
        final_prompt = _build_prompt(
            prompt,
            kind=kind,
            style=style,
            target_id=target_id,
        )

        body = {
            "model": model_name,
            "prompt": final_prompt,
            "size": _DEFAULT_SIZE,
        }

        # Seed support is optional across providers/models.
        # Keep it explicit and inspectable, but do not rely on it.
        if isinstance(seed, int):
            body["user"] = f"rpg-seed:{seed}"

        request = urllib.request.Request(
            _OPENAI_IMAGES_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            try:
                raw_error = exc.read().decode("utf-8", errors="replace")
            except Exception:
                raw_error = ""

            error_text = raw_error.lower()
            moderation_status = "blocked" if "safety" in error_text or "policy" in error_text else "approved"
            status = "blocked" if moderation_status == "blocked" else "failed"
            moderation_reason = raw_error[:500]

            return ImageGenerationResult(
                ok=False,
                status=status,
                error=f"openai_http_{exc.code}",
                moderation_status=moderation_status,
                moderation_reason=moderation_reason,
            )
        except urllib.error.URLError:
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="openai_network_error",
                moderation_status="approved",
                moderation_reason="",
            )
        except Exception:
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="openai_unexpected_error",
                moderation_status="approved",
                moderation_reason="",
            )

        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="openai_invalid_json",
                moderation_status="approved",
                moderation_reason="",
            )

        return _extract_result(payload)