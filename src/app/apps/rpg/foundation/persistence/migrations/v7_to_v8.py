"""RQ-1.1: migration v7 to v8.

Package format 8 can carry a whole campaign document (``campaign.document``, at ``campaign.document_version``,
v6 or later) beside the creator setup and simulation state that packages 1-7 carry. A v7 package carries no
campaign document; it gains an empty ``campaign`` section.
"""
from __future__ import annotations

from typing import Any


def migrate_v7_to_v8(package: dict[str, Any]) -> dict[str, Any]:
    package = dict(package or {})
    campaign = package.get("campaign")
    package["campaign"] = dict(campaign) if isinstance(campaign, dict) else {"document_version": None, "document": None}
    package["schema_version"] = 8
    return package
