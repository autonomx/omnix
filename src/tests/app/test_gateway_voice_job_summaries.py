from __future__ import annotations

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app
from app.jobs import JobRecord, JobStatus, ResourceClass
from app.jobs.models import JobProgress, JobStage


class FakeVoiceJobStore:
    def __init__(self, jobs: list[JobRecord]) -> None:
        self.jobs = jobs

    def list_jobs(self) -> list[JobRecord]:
        return self.jobs


def make_job(job_id: str, module: str, audio_payload: str) -> JobRecord:
    return JobRecord(
        id=job_id,
        module=module,
        type="tts.synthesize",
        status=JobStatus.COMPLETED,
        resource_class=ResourceClass.GPU_TTS,
        stages=[
            JobStage(
                id="synthesize",
                label="Synthesize",
                status=JobStatus.COMPLETED,
                resource_class=ResourceClass.GPU_TTS,
                progress=JobProgress(current=1, total=1),
                output_refs=[{"data_url": audio_payload, "stage_note": "s" * 4_000}],
            )
        ],
        progress=JobProgress(current=1, total=1),
        logs=[{"message": "done", "debug_blob": "l" * 4_000}],
        input_payload={"text": "hello", "sample_audio_base64": "i" * 4_000},
        output_refs=[
            {
                "data_url": audio_payload,
                "title": job_id,
                "oversized_note": "n" * 4_000,
            }
        ],
        created_at="2026-07-05T00:00:00+00:00",
        updated_at="2026-07-05T00:00:00+00:00",
        completed_at="2026-07-05T00:00:00+00:00",
    )


def test_voice_job_summary_route_bounds_inline_browser_payloads(monkeypatch) -> None:
    from app.gateway import voice_job_summary_routes

    audio = "data:audio/wav;base64," + ("A" * 1_000)
    jobs = [
        make_job("voice-1", "voice", audio),
        make_job("voice-2", "voice-cloning", audio),
        make_job("voice-3", "voice", audio),
        make_job("chat-1", "chatbot", audio),
    ]
    monkeypatch.setattr(
        voice_job_summary_routes,
        "default_job_store",
        lambda: FakeVoiceJobStore(jobs),
    )
    client = TestClient(create_gateway_app())

    response = client.get("/api/jobs/voice-summaries?limit=3")

    assert response.status_code == 200
    payload = response.json()
    assert [job["id"] for job in payload["jobs"]] == ["voice-1", "voice-2", "voice-3"]

    first, second, third = payload["jobs"]
    assert first["output_refs"][0]["data_url"].startswith("data:audio/")
    assert second["output_refs"][0]["data_url"].startswith("data:audio/")
    assert "data_url" not in third["output_refs"][0]
    assert third["output_refs"][0]["data_url_omitted"] is True

    for job in payload["jobs"]:
        assert "sample_audio_base64" not in job["input_payload"]
        assert job["input_payload"]["sample_audio_base64_omitted"] is True
        assert "data_url" not in job["stages"][0]["output_refs"][0]
        assert job["stages"][0]["output_refs"][0]["data_url_omitted"] is True
        assert "debug_blob" not in job["logs"][0]
        assert job["logs"][0]["debug_blob_omitted"] is True
        assert "oversized_note" not in job["output_refs"][0]
        assert job["output_refs"][0]["oversized_note_omitted"] is True
