from app.jobs.inline_execution_compat import mark_inline_execution
from app.jobs.models import CreateJobRequest, ResourceClass
from app.persistence.job_compat import PostgresJobStoreAdapter


def test_mark_inline_execution_preserves_existing_compatibility_flags() -> None:
    request = CreateJobRequest(
        module="voice",
        type="tts.multi_speaker_synthesize",
        resource_class=ResourceClass.CPU,
        compat={"client_contract": "voice_studio_v2"},
    )

    marked = mark_inline_execution(request)

    assert marked.compat == {
        "client_contract": "voice_studio_v2",
        "inline_execution": True,
    }
    assert request.compat == {"client_contract": "voice_studio_v2"}


def test_postgres_compat_logs_preserve_structured_entries() -> None:
    structured = {"level": "info", "message": "audio saved", "content": "path.wav"}

    assert PostgresJobStoreAdapter._compat_log(structured) == structured
    assert PostgresJobStoreAdapter._compat_log("legacy log") == {
        "level": "info",
        "message": "legacy log",
    }
