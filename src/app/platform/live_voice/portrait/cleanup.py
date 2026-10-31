"""Forgetting a portrait no pack shows any more (live portrait roadmap, Phase 4, "Cleanup").

The portrait service keeps each prepared portrait's encoding and idle loop by (tenant, image digest). When the
characters module says no portrait pack in the tenant shows an image any more, this asks the service to forget
it (``DELETE /portrait/cache/{tenant}/{image_sha256}``), off the request's thread. Nothing else holds a
portrait's data: the idle loop lives with the encoding on the service.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Callable
from typing import Any

from .link import portrait_url

logger = logging.getLogger(__name__)

MAX_PORTRAIT_BYTES = 12 * 1024 * 1024


def _default_asset_store() -> Any:
    from app.assets import default_asset_store

    return default_asset_store()


def _forget(base_url: str, tenant: str, digest: str) -> None:
    import httpx

    from app.security.service_token import service_headers

    try:
        httpx.delete(f"{base_url}/portrait/cache/{tenant}/{digest}", headers=service_headers(), timeout=5.0)
    except httpx.HTTPError:
        logger.info("The portrait service did not answer; it forgets the portrait when it unloads", exc_info=True)


class PortraitCacheCleaner:
    """A ``PORTRAIT_IMAGE_OBSERVERS`` implementation: the service forgets a released portrait."""

    def __init__(self, asset_store_factory: Callable[[], Any] = _default_asset_store,
                 forget: Callable[[str, str, str], None] = _forget, background: bool = True) -> None:
        self.asset_store_factory = asset_store_factory
        self.forget = forget
        self.background = background

    def on_portrait_released(self, asset_id: str) -> None:
        base_url = portrait_url()
        if not base_url:
            return
        from app.runtime.tenant_context import current_tenant

        # The digest the service was given at prepare: of the image's bytes, as the gateway read them.
        image = self.asset_store_factory().read_asset_bytes(asset_id, max_bytes=MAX_PORTRAIT_BYTES)
        digest = hashlib.sha256(image).hexdigest()
        tenant = current_tenant().workspace_id
        if self.background:
            threading.Thread(target=self.forget, args=(base_url, tenant, digest), name="omnix-portrait-forget",
                             daemon=True).start()
        else:
            self.forget(base_url, tenant, digest)


__all__ = ["PortraitCacheCleaner"]
