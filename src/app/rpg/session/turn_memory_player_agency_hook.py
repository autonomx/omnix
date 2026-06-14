from __future__ import annotations

from types import ModuleType


def preserve_player_agency_hook(module: ModuleType) -> None:
    try:
        from app.rpg.session.player_agency_runtime_hook import force_install_player_agency_runtime_hook_for_tests

        force_install_player_agency_runtime_hook_for_tests(module)
    except Exception:
        return
