# AI module for RPG system.
#
# Keep package import lightweight. Do not eagerly import legacy/optional AI modules
# here because tests and focused runtime imports often only need one submodule
# such as app.rpg.ai.conversation_threads.

try:
    from app.rpg.ai.world_scene_survival_grounding_bridge import (
        install_world_scene_survival_grounding_hook,
    )

    install_world_scene_survival_grounding_hook()
except Exception:
    # Package import must remain best-effort/lightweight. Focused modules can
    # still call force_patch_world_scene_narrator() in tests or runtime setup.
    pass

__all__ = []
