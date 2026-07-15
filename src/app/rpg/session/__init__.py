"""Phase 13.5 + 15.0 — Session lifecycle + persistence module."""
# Phase 15.0 — Durable persistence
from .autoplay_certification_artifact import (
    append_saved_100_turn_certification_to_campaign_report_html,
    assert_phase7_real_autoplay_certification_artifact_ready,
    build_real_autoplay_certification_artifact,
    build_saved_100_turn_certification_payload,
    render_saved_100_turn_certification_report_html,
)
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
from .saved_autoplay_digest_sources import (
    assert_phase7_saved_autoplay_digest_source_ready,
    build_saved_autoplay_digest_source_contract,
    capture_saved_autoplay_digest_sources,
)
from .session_store import (
    archive_session,
    ensure_session_registry,
    get_session,
    list_sessions,
    save_session,
)
from .turn_certification import (
    assert_phase7_full_100_turn_certification_ready,
    build_full_100_turn_certification_contract,
    build_full_100_turn_certification_result,
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


def _try_install_optional_hook(import_path: str, installer_name: str) -> None:
    try:
        module_name, _, attr_name = import_path.rpartition(".")
        module = __import__(module_name, fromlist=[attr_name])
        installer = getattr(module, installer_name or attr_name)
        installer()
    except Exception:
        return


def _install_optional_fast_runtime_hooks() -> None:
    # These hooks are best-effort and independent. A failure in an older hook
    # must not abort later P0 latency hooks such as fast visible dialogue or the
    # visible-response guard.
    for import_path, installer_name in (
        ("app.rpg.session.fast_combat_narration_skip.install_fast_combat_narration_skip", "install_fast_combat_narration_skip"),
        ("app.rpg.session.fast_combat_presentation_hook.install_fast_combat_presentation_hook", "install_fast_combat_presentation_hook"),
        ("app.rpg.session.interactive_fast_combat_result_hook.install_interactive_fast_combat_result_hook", "install_interactive_fast_combat_result_hook"),
        ("app.rpg.session.player_agency_runtime_hook.install_player_agency_runtime_hook", "install_player_agency_runtime_hook"),
        ("app.rpg.session.npc_dialogue_repair_hook.install_npc_dialogue_repair_hook", "install_npc_dialogue_repair_hook"),
        ("app.rpg.session.interpretive_adjudication.install_interpretive_adjudication_hook", "install_interpretive_adjudication_hook"),
        ("app.rpg.session.first_call_dialogue_guard.install_first_call_dialogue_placeholder_guard", "install_first_call_dialogue_placeholder_guard"),
        ("app.rpg.session.hypothetical_world_resolution.install_hypothetical_world_resolution", "install_hypothetical_world_resolution"),
        ("app.rpg.session.contract_attachment.install_contract_attachment", "install_contract_attachment"),
        ("app.rpg.session.diegetic_fallback_hook.install_diegetic_fallback_hook", "install_diegetic_fallback_hook"),
        ("app.rpg.session.fast_visible_dialogue_hook.install_fast_visible_dialogue_hook", "install_fast_visible_dialogue_hook"),
        ("app.rpg.session.visible_response_runtime_hook.install_visible_response_runtime_guard", "install_visible_response_runtime_guard"),
        ("app.rpg.session.session_performance_hook.install_session_performance_hook", "install_session_performance_hook"),
        ("app.rpg.session.interaction_event_store_hook.install_interaction_event_store_hook", "install_interaction_event_store_hook"),
        ("app.rpg.session.dialogue_quality_hook.install_dialogue_quality_hook", "install_dialogue_quality_hook"),
        ("app.rpg.session.interaction_timeline_hook.install_interaction_timeline_hook", "install_interaction_timeline_hook"),
        ("app.rpg.session.interaction_lifecycle_hook.install_interaction_lifecycle_hook", "install_interaction_lifecycle_hook"),
        ("app.rpg.session.narrative_engine_direct_dialogue_hook.install_interactive_direct_dialogue_cutover", "install_interactive_direct_dialogue_cutover"),
        ("app.rpg.debug_runtime_hook.install_rpg_runtime_debug_hook", "install_rpg_runtime_debug_hook"),
    ):
        _try_install_optional_hook(import_path, installer_name)


_install_optional_fast_runtime_hooks()

__all__ = [
    "archive_session",
    "ensure_session_registry",
    "get_session",
    "list_sessions",
    "save_session",
    "list_sessions_from_disk",
    "load_session_from_disk",
    "save_session_to_disk",
    "assert_phase7_replay_checkpoint_foundation_ready",
    "build_replay_checkpoint_contract",
    "build_session_checkpoint",
    "canonical_session_json",
    "compare_session_checkpoints",
    "restore_session_from_checkpoint",
    "session_checkpoint_digest",
    "assert_phase7_replay_turn_sequence_ready",
    "build_replay_turn_sequence_contract",
    "default_replay_command_handlers",
    "run_replay_turn_sequence",
    "validate_replay_turn_sequence",
    "assert_phase7_save_load_replay_roundtrip_ready",
    "build_save_load_replay_roundtrip_contract",
    "run_save_load_replay_persistence_roundtrip",
    "assert_phase7_100_turn_readiness_ready",
    "build_100_turn_readiness_contract",
    "build_100_turn_readiness_result",
    "append_100_turn_readiness_report_to_campaign_report_html",
    "assert_phase7_100_turn_readiness_report_ready",
    "build_100_turn_readiness_report_contract",
    "build_100_turn_readiness_report_payload",
    "render_100_turn_readiness_report_html",
    "assert_phase7_full_100_turn_certification_ready",
    "build_full_100_turn_certification_contract",
    "build_full_100_turn_certification_result",
    "append_saved_100_turn_certification_to_campaign_report_html",
    "assert_phase7_real_autoplay_certification_artifact_ready",
    "build_real_autoplay_certification_artifact",
    "build_saved_100_turn_certification_payload",
    "render_saved_100_turn_certification_report_html",
]
