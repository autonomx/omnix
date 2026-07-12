from __future__ import annotations


def test_same_active_rpg_turn_job_reuses_existing_job(tmp_path, monkeypatch) -> None:
    import app.jobs
    from app.jobs import CreateJobRequest, ResourceClass, SQLiteJobStore, inline_feature_jobs

    monkeypatch.setattr(inline_feature_jobs, "_start_background_feature_job", lambda *args, **kwargs: None)

    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    request = CreateJobRequest(
        module="rpg",
        type="rpg.turn",
        resource_class=ResourceClass.CPU,
        input_ref={"session_id": "session-1"},
        input_payload={"command": "i ask bran how his day is going"},
    )

    first = store.create_job(request)
    second = store.create_job(request)

    assert app.jobs is not None
    assert second.id == first.id
    assert [job.id for job in store.list_jobs() if job.type == "rpg.turn"] == [first.id]


def test_distinct_rpg_turn_commands_create_distinct_jobs(tmp_path, monkeypatch) -> None:
    from app.jobs import CreateJobRequest, ResourceClass, SQLiteJobStore, inline_feature_jobs

    monkeypatch.setattr(inline_feature_jobs, "_start_background_feature_job", lambda *args, **kwargs: None)

    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    first = store.create_job(
        CreateJobRequest(
            module="rpg",
            type="rpg.turn",
            resource_class=ResourceClass.CPU,
            input_ref={"session_id": "session-1"},
            input_payload={"command": "i ask bran how his day is going"},
        )
    )
    second = store.create_job(
        CreateJobRequest(
            module="rpg",
            type="rpg.turn",
            resource_class=ResourceClass.CPU,
            input_ref={"session_id": "session-1"},
            input_payload={"command": "i ask bran how business is going"},
        )
    )

    assert second.id != first.id


def test_rpg_turn_visible_text_collapses_repeated_speaker_line() -> None:
    import app.jobs
    from app.jobs import inline_feature_jobs

    text = inline_feature_jobs._rpg_turn_visible_text(
        {
            "visible_response": {
                "narration": "Bran: It's been a fairly steady day, actually.",
                "npc": {"speaker": "Bran", "line": "It's been a fairly steady day, actually."},
            }
        }
    )

    assert app.jobs is not None
    assert text == "Bran: It's been a fairly steady day, actually."
