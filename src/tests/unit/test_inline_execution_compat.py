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


def test_postgres_compat_lease_uses_persisted_start_as_claim_time() -> None:
    adapter = object.__new__(PostgresJobStoreAdapter)
    record = adapter._record(
        {
            "id": "job:leased",
            "owner_user_id": "user:local",
            "module": "rpg",
            "job_type": "rpg.turn",
            "status": "leased",
            "resource_class": "cpu",
            "priority": 0,
            "progress": {},
            "input_payload": {},
            "output_refs": [],
            "error": None,
            "lease_owner": "worker:rpg",
            "lease_token": "lease-token",
            "lease_expires_at": "2026-07-16T02:00:00+00:00",
            "started_at": "2026-07-16T01:00:00+00:00",
            "completed_at": None,
            "created_at": "2026-07-16T00:59:00+00:00",
            "updated_at": "2026-07-16T01:00:01+00:00",
            "metadata": {},
        }
    )

    assert record.lease is not None
    assert record.lease.claimed_at == "2026-07-16T01:00:00+00:00"
    assert record.lease.expires_at == "2026-07-16T02:00:00+00:00"


def test_postgres_compat_normalizes_legacy_code_only_error() -> None:
    adapter = object.__new__(PostgresJobStoreAdapter)
    record = adapter._record(
        {
            "id": "job:expired",
            "owner_user_id": "user:local",
            "module": "rpg",
            "job_type": "rpg.campaign_genesis.generate",
            "status": "failed",
            "resource_class": "rpg_campaign_genesis",
            "priority": 0,
            "progress": {},
            "input_payload": {},
            "output_refs": [],
            "error": {"code": "lease_expired"},
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "created_at": "2026-07-16T00:00:00Z",
            "updated_at": "2026-07-16T00:01:00Z",
            "started_at": "2026-07-16T00:00:10Z",
            "completed_at": "2026-07-16T00:01:00Z",
            "metadata": {},
        }
    )

    assert record.error is not None
    assert record.error.code == "lease_expired"
    assert record.error.message == "lease_expired"
