from __future__ import annotations

from pathlib import Path

from app.desktop_companion.evaluation import (
    DesktopCompanionEvaluationCreate,
    DesktopCompanionEvaluationStore,
    hash_vision_model_id,
)
from app.desktop_companion.qualification import (
    build_desktop_companion_qualification_report,
    main,
    qualification_exit_code,
    render_desktop_companion_qualification_markdown,
)
from app.desktop_companion.release_gate import DesktopCompanionEvidencePartition

COMMIT_SHA = "2a1a4830efc3b4294702df9d960a0aaf42a96b92"
MODEL_HASH = hash_vision_model_id("qualification-model")
BASE_SCENARIOS = (
    "static-screen",
    "typing",
    "rapid-browsing",
    "scene-change",
    "interruption",
    "screen-prompt-injection",
)
SPEECH_SCENARIOS = (*BASE_SCENARIOS, "speech-completed", "speech-stale")


def create_record(index: int, *, stage: str = "text", speech: bool = False) -> DesktopCompanionEvaluationCreate:
    scenarios = SPEECH_SCENARIOS if speech else BASE_SCENARIOS
    counts = {
        "max_vision_calls_per_minute": 6,
        "observations": 20,
        "deliveries": 1 if speech else 0,
    }
    return DesktopCompanionEvaluationCreate(
        run_id=f"qualification:{stage}:{index}",
        session_id=f"chat:{index}",
        started_at=f"2026-07-15T05:{index:02d}:00Z",
        ended_at=f"2026-07-15T05:{index:02d}:30Z",
        exact_commit_sha=COMMIT_SHA,
        rollout_stage=stage,
        vision_provider="openai-compatible-local",
        vision_model_hash=MODEL_HASH,
        remote_provider=False,
        counts=counts,
        latency_ms={"observation_p95": 4_000},
        rates={
            "stale_output_rate": 0.0,
            "duplicate_comment_rate": 0.0,
            "unsupported_claim_rate": 0.0,
            "collision_rate": 0.0,
            "provider_error_rate": 0.0,
        },
        scenario_labels=[scenarios[index % len(scenarios)]],
    )


def partition() -> DesktopCompanionEvidencePartition:
    return DesktopCompanionEvidencePartition(
        exact_commit_sha=COMMIT_SHA,
        observation_schema_version=1,
        attention_policy_version=1,
        vision_provider="openai-compatible-local",
        vision_model_hash=MODEL_HASH,
        remote_provider=False,
    )


def records(tmp_path: Path, *, stage: str = "text", speech: bool = False):
    store = DesktopCompanionEvaluationStore(tmp_path / f"{stage}.json")
    values = [store.upsert(create_record(index, stage=stage, speech=speech)) for index in range(12)]
    return store, values


def test_text_qualification_passes_one_exact_partition(tmp_path: Path) -> None:
    _, values = records(tmp_path)

    report = build_desktop_companion_qualification_report(values, partition=partition(), stage="text")

    assert report.status == "pass"
    assert report.recommendation == "eligible_for_text_rollout"
    assert report.records_scanned == 12
    assert report.failures == ()
    assert qualification_exit_code(report.status) == 0


def test_speech_qualification_requires_speech_specific_evidence(tmp_path: Path) -> None:
    _, text_values = records(tmp_path)
    report = build_desktop_companion_qualification_report(text_values, partition=partition(), stage="speech")

    assert report.status == "insufficient"
    assert report.recommendation == "collect_more_exact_partition_evidence"
    assert any(value.startswith("minimum_speech_records:") for value in report.insufficient)
    assert qualification_exit_code(report.status) == 2

    _, speech_values = records(tmp_path, stage="speech", speech=True)
    speech_report = build_desktop_companion_qualification_report(
        speech_values,
        partition=partition(),
        stage="speech",
    )
    assert speech_report.status == "pass"
    assert speech_report.recommendation == "eligible_for_speech_rollout"


def test_markdown_report_is_content_free(tmp_path: Path) -> None:
    _, values = records(tmp_path)
    report = build_desktop_companion_qualification_report(values, partition=partition(), stage="text")

    rendered = render_desktop_companion_qualification_markdown(report)

    assert "Status: **PASS**" in rendered
    assert COMMIT_SHA in rendered
    assert "data:image" not in rendered
    assert "screen text" not in rendered.casefold()


def test_cli_reads_evidence_store_and_returns_stable_exit_code(tmp_path: Path, capsys) -> None:
    store, _ = records(tmp_path)

    exit_code = main(
        [
            "--stage",
            "text",
            "--exact-commit-sha",
            COMMIT_SHA,
            "--evidence-path",
            str(store.path),
            "--vision-provider",
            "openai-compatible-local",
            "--vision-model-hash",
            MODEL_HASH,
            "--remote-provider",
            "false",
            "--format",
            "json",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"status": "pass"' in output
    assert '"records_scanned": 12' in output
