"""Final Omnix persistence retirement hook loaded after ``sitecustomize``."""

from __future__ import annotations

import os


if (os.environ.get("OMNIX_PERSISTENCE_MODE") or "postgresql").strip().lower() == "postgresql":
    from app.persistence.legacy_authority_block import install_legacy_authority_block

    install_legacy_authority_block()
