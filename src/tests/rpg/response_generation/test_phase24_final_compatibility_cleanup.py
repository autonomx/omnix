from __future__ import annotations

from pathlib import Path

from app.jobs.models import CreateJobRequest, ResourceClass
from app.jobs.rpg_turn_job_guard import RPG_FOREGROUND_RECORD_TYPE
from app.jobs.store import SQLiteJobStore

_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_foreground_record_retires_synthetic_compatibility_metadata(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    job = store.create_job(
        CreateJobRequest(
            module="rpg",
            type=RPG_FOREGROUND_RECORD_TYPE,
            resource_class=ResourceClass.CPU,
            input_ref={"session_id": "session:test"},
            input_payload={"submission_id": "submit:test", "command": "Continue."},
            compat={
                "synthetic_job_mirror": True,
                "direct_foreground_route": True,
                "record_only": True,
            },
        )
    )

    assert job.compat == {"foreground_record": True, "record_only": True}
    persisted = store.get_job(job.id)
    assert persisted is not None
    assert persisted.compat == {"foreground_record": True, "record_only": True}


def test_deleted_gateway_compatibility_paths_remain_absent() -> None:
    gateway = _REPO_ROOT / "src" / "app" / "gateway"

    assert not (gateway / "rpg_visible_response_bridge.py").exists()
    assert not (gateway / "rpg_direct_turn_routes.py").exists()
    assert "_foreground_turn_text" not in (gateway / "rpg_session_routes.py").read_text(encoding="utf-8")
    assert "_visible_turn_text" not in (gateway / "rpg_turn_job_mirror.py").read_text(encoding="utf-8")


def test_active_inline_job_path_overrides_legacy_private_formatter() -> None:
    package_source = (
        _REPO_ROOT / "src" / "app" / "jobs" / "inline_feature_jobs" / "__init__.py"
    ).read_text(encoding="utf-8")

    assert "visible_response_text" in package_source
    assert "_source._rpg_turn_visible_text = _canonical_rpg_turn_visible_text" in package_source
