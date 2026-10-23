"""Where a model service finds an installed model's files in the desktop app (desktop roadmap §4.6).

The desktop app keeps every model in the Hugging Face cache under its packs
folder, at the catalog's pinned commit. Services that load by repository id
(NeMo's ``from_pretrained``) find them there through the pinned ``refs/main``
with ``HF_HUB_OFFLINE=1``. Services that load from a folder ask here for the
pinned snapshot. Outside the desktop app this returns nothing, and those
services keep their usual folders (``resources/models/...``).
"""
from __future__ import annotations

from pathlib import Path


def installed_snapshot(model_id: str) -> Path | None:
    """The pinned snapshot folder of an installed model, in the desktop app; None otherwise."""
    from app.models import packs

    if not packs.desktop_mode():
        return None
    try:
        store = packs.model_store()
        if store.installed(model_id):
            return store.snapshot(model_id)
    except (KeyError, packs.PackError):
        return None
    return None


__all__ = ["installed_snapshot"]
