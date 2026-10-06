"""Phase 7.9 — Pack Schema Helpers.

Helper schema constructors and canonicalization for adventure packs.
"""

from __future__ import annotations


from .models import AdventurePack, PackContent, PackManifest, PackMetadata


def build_empty_pack(pack_id: str, title: str, version: str) -> AdventurePack:
    """Build a minimal valid adventure pack with empty content."""
    return AdventurePack(
        metadata=PackMetadata(
            pack_id=pack_id,
            title=title,
            version=version,
        ),
        manifest=PackManifest(
            manifest_id=f"{pack_id}_manifest",
            pack_id=pack_id,
            content_version=version,
        ),
        content=PackContent(),
    )


