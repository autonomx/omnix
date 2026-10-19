"""Launcher settings (WP-11.4); they live in the config layer, ``app.config.launcher``.

Providers resolve their interpreters there too (the Fish S2 Pro server), and a
provider may not import the composition layer. This module keeps the launcher's
own import path.
"""
from __future__ import annotations

from app.config.launcher import CONFIG_RELATIVE_PATH, LauncherConfig, load_launcher_config

__all__ = ["CONFIG_RELATIVE_PATH", "LauncherConfig", "load_launcher_config"]
