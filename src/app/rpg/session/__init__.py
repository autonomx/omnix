"""Phase 13.5 + 15.0 — Session lifecycle + persistence module."""
# Phase 15.0 — Durable persistence
from .durable_store import (
    list_sessions_from_disk,
    load_session_from_disk,
    save_session_to_disk,
)
from .replay_checkpoint import (
    assert_phase7_replay_checkpoint_foundation_ready,
    build_replay_checkpoint_contract,
    build_session_checkpoint,
    canonical_session_json,
    compare_session_checkpoints,
    restore_session_from_checkpoint,
    session_checkpoint_digest,
)
from .replay_persistence_roundtrip_v2 import (
    assert_phase7_save_load_replay_roundtrip_ready,
    build_save_load_replay_roundtrip_contract,
    run_save_load_replay_persistence_roundtrip,
)
from .replay_turn_sequence import (
    assert_phase7_replay_turn_sequence_ready,
    build_replay_turn_sequence_contract,
    default_replay_command_handlers,
    run_replay_turn_sequence,
    validate_replay_turn_sequence,
)
from .session_store import (
    archive_session,
    ensure_session_registry,
    get_session,
    list_sessions,
    save_session,
)
from .turn_readiness import (
    assert_phase7_100_turn_readiness_ready,
    build_100_turn_readiness_contract,
    build_100_turn_readiness_result,
)
from .turn_readiness_report import (
    append_100_turn_readiness_report_to_campaign_report_html,
    assert_phase7_100_turn_readiness_report_ready,
    build_100_turn_readiness_report_contract,
    build_100_turn_readiness_report_payload,
    render_100_turn_readiness_report_html,
)


def _install_optional_fast_runtime_hooks() -> None:
    try:
        from .fast_combat_narration_skip import install_fast_combat_narration_skip

        install_fast_combat_narration_skip()
    except Exception:
        # Runtime hook installation must never block normal session imports.
        return

    try:
        from .fast_combat_presentation_hook import install_fast_combat_presentation_hook

        install_fast_combat_presentation_hook()
    except Exception:
        # Presentation hook installation must never block normal session imports.
        return

    try:
        from .interactive_fast_combat_result_hook import install_interactive_fast_combat_result_hook

        install_interactive_fast_combat_result_hook()
    except Exception:
        # Interactive result hook installation must never block normal session imports.
        return


_install_optional_fast_runtime_hooks()

__all__ = [
    "archive_session",
    "ensure_session_registry",
    "get_session",
    "list_sessions",
    "save_session",
    # Phase 15.0
    "list_sessions_from_disk",
    "load_session_from_disk",
    "save_session_to_disk",
    # Phase 7.1
    "assert_phase7_replay_checkpoint_foundation_ready",
    "build_replay_checkpoint_contract",
    "build_session_checkpoint",
    "canonical_session_json",
    "compare_session_checkpoints",
    "restore_session_from_checkpoint",
    "session_checkpoint_digest",
    # Phase 7.2
    "assert_phase7_replay_turn_sequence_ready",
    "build_replay_turn_sequence_contract",
    "default_replay_command_handlers",
    "run_replay_turn_sequence",
    "validate_replay_turn_sequence",
    # Phase 7.3
    "assert_phase7_save_load_replay_roundtrip_ready",
    "build_save_load_replay_roundtrip_contract",
    "run_save_load_replay_persistence_roundtrip",
    # Phase 7.4
    "assert_phase7_100_turn_readiness_ready",
    "build_100_turn_readiness_contract",
    "build_100_turn_readiness_result",
    # Phase 7.5
    "append_100_turn_readiness_report_to_campaign_report_html",
    "assert_phase7_100_turn_readiness_report_ready",
    "build_100_turn_readiness_report_contract",
    "build_100_turn_readiness_report_payload",
    "render_100_turn_readiness_report_html",
]
