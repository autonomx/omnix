import json
import zipfile
from types import SimpleNamespace


REQUIRED_OUTPUT_FILES = {
    "autoplay-summary.json",
    "autoplay-transcript.json",
    "autoplay-campaign-results.zip",
}
REQUIRED_SUMMARY_FIELDS = {
    "ok",
    "turns_executed",
    "health",
    "transcript_rows",
    "artifact_paths",
}
REQUIRED_ARTIFACT_PATH_KEYS = {
    "summary",
    "transcript",
    "zip",
}
REQUIRED_ZIP_MEMBERS = {
    "summary.json",
    "autoplay-transcript.json",
}


def test_phase9_2_endurance_artifact_contract_doc_records_required_outputs():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    doc = (
        root / "docs" / "plans" / "rpg_phase9_2_endurance_artifact_contract.md"
    ).read_text(encoding="utf-8")

    for expected in (
        "run_autoplay_campaign(args)",
        "autoplay-summary.json",
        "autoplay-transcript.json",
        "autoplay-campaign-results.zip",
        "summary.json",
        "artifact_contract_failure",
        "operator_evidence_gap",
        "Phase 9.3 — endurance checkpoint and replay taxonomy guard.",
    ):
        assert expected in doc
    for field in REQUIRED_SUMMARY_FIELDS:
        assert f"`{field}`" in doc
    for key in REQUIRED_ARTIFACT_PATH_KEYS:
        assert f"`{key}`" in doc


def test_phase9_2_run_autoplay_campaign_writes_summary_transcript_and_zip(
    tmp_path,
    monkeypatch,
):
    import tests.rpg.autoplay_llm_campaign as campaign

    def fake_prepare_autoplay_manual_session(**kwargs):
        return {
            "session_id": kwargs["session_id"],
            "simulation_state": {"turns": []},
        }

    def fake_call_turn_runtime(
        *,
        session_id,
        simulation_state,
        turn_index,
        player_action,
        runtime_narration,
    ):
        turns = list(simulation_state.get("turns", []))
        turns.append(
            {
                "turn_index": turn_index,
                "player_action": player_action,
                "runtime_narration": runtime_narration,
                "session_id": session_id,
            }
        )
        return {
            "ok": True,
            "simulation_state": {"turns": turns},
            "turn_runtime": {"phase9_2_fixture": True},
            "narration": f"deterministic turn {turn_index}",
        }

    monkeypatch.setattr(
        campaign,
        "prepare_autoplay_manual_session",
        fake_prepare_autoplay_manual_session,
    )
    monkeypatch.setattr(campaign, "_call_turn_runtime", fake_call_turn_runtime)
    monkeypatch.setattr(
        campaign,
        "validate_save_load_checkpoint",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        campaign,
        "post_objective_false_progress_warnings",
        lambda transcript_rows: [],
    )

    args = SimpleNamespace(
        turns=3,
        session_id="phase9_2_artifact_contract",
        output_dir=str(tmp_path),
        narration_mode="blocking",
    )

    summary = campaign.run_autoplay_campaign(args)

    assert REQUIRED_OUTPUT_FILES <= {path.name for path in tmp_path.iterdir()}
    summary_path = tmp_path / "autoplay-summary.json"
    transcript_path = tmp_path / "autoplay-transcript.json"
    zip_path = tmp_path / "autoplay-campaign-results.zip"
    disk_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    transcript_rows = json.loads(transcript_path.read_text(encoding="utf-8"))

    assert REQUIRED_SUMMARY_FIELDS <= set(disk_summary)
    assert disk_summary == summary
    assert disk_summary["ok"] is True
    assert disk_summary["turns_executed"] == 3
    assert isinstance(disk_summary["health"], dict)
    assert isinstance(disk_summary["transcript_rows"], list)
    assert len(disk_summary["transcript_rows"]) == 3
    assert transcript_rows == disk_summary["transcript_rows"]
    assert REQUIRED_ARTIFACT_PATH_KEYS <= set(disk_summary["artifact_paths"])
    assert disk_summary["artifact_paths"]["summary"] == str(summary_path)
    assert disk_summary["artifact_paths"]["transcript"] == str(transcript_path)
    assert disk_summary["artifact_paths"]["zip"] == str(zip_path)

    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
        zipped_summary = json.loads(archive.read("summary.json").decode("utf-8"))
        zipped_transcript = json.loads(
            archive.read("autoplay-transcript.json").decode("utf-8")
        )

    assert REQUIRED_ZIP_MEMBERS <= names
    assert REQUIRED_SUMMARY_FIELDS <= set(zipped_summary)
    assert zipped_summary["artifact_paths"] == {}
    assert zipped_transcript == transcript_rows


def test_phase9_2_contract_guard_is_provider_free_source_backed():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    harness = (root / "src" / "tests" / "rpg" / "autoplay_llm_campaign.py").read_text(
        encoding="utf-8"
    )

    guarded_source = harness.split("def run_autoplay_campaign(args):", 1)[1]
    guarded_source = guarded_source.split("if __name__ != \"__main__\":", 1)[0]

    for required in REQUIRED_OUTPUT_FILES:
        assert required in guarded_source
    for required in REQUIRED_ZIP_MEMBERS:
        assert required in guarded_source
    for field in REQUIRED_SUMMARY_FIELDS:
        assert f'"{field}"' in guarded_source
    for forbidden in (
        "openai",
        "anthropic",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "LM_STUDIO",
        "LMSTUDIO",
    ):
        assert forbidden not in guarded_source
