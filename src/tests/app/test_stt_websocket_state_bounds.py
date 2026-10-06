import asyncio
from types import SimpleNamespace

import pytest

from app.providers import nemotron_eou_live_websocket as nemotron
from app.providers import stt_live_websocket as stt


def test_nemotron_session_state_is_bounded_expiring_and_invalidatable(monkeypatch) -> None:
    nemotron.clear_nemotron_session_states()
    monkeypatch.setattr(nemotron, "MAX_SESSION_STATES", 2)
    monkeypatch.setattr(nemotron, "SESSION_TTL_SECONDS", 5.0)
    now = {"value": 10.0}
    monkeypatch.setattr(nemotron.time, "monotonic", lambda: now["value"])

    first = nemotron._session_state("first")
    nemotron._session_state("second")
    nemotron._session_state("third")
    assert list(nemotron._SESSION_STATES) == ["second", "third"]

    now["value"] = 16.0
    assert nemotron._session_state("fresh").session_id == "fresh"
    assert len(nemotron._SESSION_STATES) == 1
    nemotron.clear_nemotron_session_states()
    assert not nemotron._SESSION_STATES
    assert first.session_id == "first"


def test_nemotron_does_not_evict_sessions_with_open_segments(monkeypatch) -> None:
    nemotron.clear_nemotron_session_states()
    monkeypatch.setattr(nemotron, "MAX_SESSION_STATES", 1)
    monkeypatch.setattr(nemotron.time, "monotonic", lambda: 10.0)
    active = nemotron._session_state("active")
    active.segments["segment"] = object()

    with pytest.raises(RuntimeError, match="capacity"):
        nemotron._session_state("next")
    nemotron.clear_nemotron_session_states()


def test_stt_session_state_has_explicit_invalidation() -> None:
    stt.clear_stt_session_states()
    state = stt._session_state("session")

    assert stt._SESSION_STATES[state.session_id] is state
    stt.clear_stt_session_states()
    assert not stt._SESSION_STATES


@pytest.mark.anyio
async def test_provider_scheduler_registry_expires_and_closes_idle_schedulers(monkeypatch) -> None:
    await stt.clear_provider_schedulers()
    now = {"value": 10.0}
    closed: list[object] = []

    class FakeScheduler:
        queued_jobs = 0
        is_idle = True

        async def close(self) -> None:
            closed.append(self)

    monkeypatch.setattr(stt.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(stt, "MAX_PROVIDER_SCHEDULERS", 1)
    monkeypatch.setattr(stt, "PROVIDER_SCHEDULER_TTL_SECONDS", 5.0)
    monkeypatch.setattr(stt, "ProviderSegmentScheduler", lambda **_kwargs: FakeScheduler())
    first = stt._scheduler_for(SimpleNamespace(model=object()))

    now["value"] = 16.0
    second = stt._scheduler_for(SimpleNamespace(model=object()))
    await asyncio.sleep(0)

    assert second is not first
    assert closed == [first]
    await stt.clear_provider_schedulers()
    assert closed == [first, second]


@pytest.mark.anyio
async def test_provider_scheduler_registry_does_not_evict_active_scheduler(monkeypatch) -> None:
    await stt.clear_provider_schedulers()

    class ActiveScheduler:
        queued_jobs = 1
        is_idle = False

        async def close(self) -> None:
            raise AssertionError("active scheduler must not be evicted")

    monkeypatch.setattr(stt, "MAX_PROVIDER_SCHEDULERS", 1)
    monkeypatch.setattr(stt, "ProviderSegmentScheduler", lambda **_kwargs: ActiveScheduler())
    first_model = object()
    second_model = object()
    stt._scheduler_for(SimpleNamespace(model=first_model))

    with pytest.raises(stt.SegmentQueueFullError, match="capacity"):
        stt._scheduler_for(SimpleNamespace(model=second_model))
    stt._PROVIDER_SCHEDULERS.clear()
