def _safe_import(module_path: str) -> None:
    """Safely import a module, ignoring import errors for optional components."""
    try:
        __import__(module_path)
    except ImportError:
        pass


# Optional runtime components - loaded if available
_safe_import("src.causality_tracker")
_safe_import("src.divergence_analyzer")
_safe_import("src.emergence_metrics")
_safe_import("src.emergence_tracker")
_safe_import("src.loop_detector")

# Core subsystems
_safe_import("app.rpg.visual")
_safe_import("app.rpg.api")
