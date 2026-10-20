"""Opt-in AudioSeal watermarking of Voice Studio renders (Phase 4; off by default).

When ``voice_watermark.enabled`` is on, every rendered take, render, restitch
and design candidate is marked after the effects chain and before it is
written, so unmarked render audio is never stored or downloadable. If the audio
service cannot mark it, the job fails instead of saving unmarked audio, and
export refuses render sources that carry no watermark.

Not marked (documented in the roadmap): live PCM streaming (chat calls and
read-aloud), voice samples and designed reference passages (they are inputs to
cloning), and audiobook chapters, which have their own pipeline.

The 16-bit message identifies the workspace (a hash of its id), so a detection
can tell whose Omnix rendered a clip.
"""
from __future__ import annotations

import hashlib
from typing import Any

SCHEME = "audioseal_wm_16bits"
SETTING_KEY = "voice_watermark"


class WatermarkUnavailable(RuntimeError):
    """Watermarking is on but the audio cannot be marked; nothing unmarked is saved."""


def watermark_enabled() -> bool:
    from app.settings.access import load_settings

    value = (load_settings() or {}).get(SETTING_KEY)
    return bool(isinstance(value, dict) and value.get("enabled"))


def set_watermark_enabled(enabled: bool) -> bool:
    from app.settings.access import save_settings

    save_settings({SETTING_KEY: {"enabled": bool(enabled)}})
    return bool(enabled)


def workspace_message() -> int:
    """The 16-bit message: a hash of the current workspace id (0 outside a workspace)."""
    try:
        from app.runtime.tenant_context import current_tenant

        workspace = str(getattr(current_tenant(), "workspace_id", "") or "")
    except Exception:
        workspace = ""
    if not workspace:
        return 0
    return int.from_bytes(hashlib.sha256(workspace.encode("utf-8")).digest()[:2], "big")


def mark(wav: bytes, *, client: Any = None) -> tuple[bytes, dict[str, Any] | None]:
    """The WAV, watermarked when the setting is on, and the record to keep on its asset."""
    if not watermark_enabled():
        return wav, None
    from .audio_service import AudioServiceClient, AudioServiceUnavailable, AudioToolRequestError

    message = workspace_message()
    try:
        marked, details = (client or AudioServiceClient()).watermark(wav, message=message)
    except (AudioServiceUnavailable, AudioToolRequestError) as exc:
        raise WatermarkUnavailable(
            f"Watermarking is on but the audio could not be marked ({exc}); nothing was saved. "
            "Start the audio service, or turn watermarking off in Audio Tools") from exc
    return marked, {"scheme": SCHEME, "message": message, **{key: details[key] for key in ("model",) if key in details}}


def is_render(asset: Any) -> bool:
    """Audio Voice Studio rendered (takes, renders, design candidates), as opposed to recordings."""
    contract = str((asset.compat or {}).get("contract") or "")
    return contract.startswith(("voice_studio_tts", "voice_studio_take", "voice_design_candidate"))


__all__ = ["SCHEME", "SETTING_KEY", "WatermarkUnavailable", "is_render", "mark", "set_watermark_enabled",
           "watermark_enabled", "workspace_message"]
