"""What the kernel reads about Dubbing without loading it (ADR-0016): kernel imports only."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.persistence.declarations import FeaturePermissions, PermissionDeclaration, SettingsSection


class DubbingSettingsProfile(BaseModel):
    """Dubbing's section of the settings profile: what a new project starts with."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    source_language: str = Field(default="en", max_length=16)
    target_language: str = Field(default="es", max_length=16)
    # The chat provider that translates; empty is the workspace's own model (local by default).
    translator: str = Field(default="", max_length=64)


SETTINGS = (SettingsSection("dubbing", DubbingSettingsProfile, order=80),)
# Projects and lines live until a person deletes the project; nothing expires on its own.
RETENTION = ()
PERMISSIONS = (
    FeaturePermissions(
        "dubbing",
        read=PermissionDeclaration("dubbing:read", "Dubbing (read)", member=True),
        write=PermissionDeclaration("dubbing:write", "Dubbing (write)", member=True),
    ),
)
