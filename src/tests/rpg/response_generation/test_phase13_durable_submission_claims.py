from __future__ import annotations

from pathlib import Path

from app.jobs.rpg_foreground_submission_store import RpgForegroundSubmissionStore


def test_submission_claim_is_unique_across_store_instances(tmp_path: Path) -> None:
    namespace = tmp_path / "jobs.sqlite"
    first_store = RpgForegroundSubmissionStore(namespace)
    second_store = RpgForegroundSubmissionStore(namespace)

    first = first_store.claim("session:one", "submit:one")
    second = second_store.claim("session:one", "submit:one")

    assert first.owner is True
    assert first.claim_token
    assert second.owner is False
    assert second.claim_token is None
    assert second.status == "claimed"
    assert not namespace.exists()

    assert first_store.complete(
        "session:one",
        "submit:one",
        str(first.claim_token),
        {"ok": True, "interaction_id": "interaction:one"},
    ) is True
    recovered = second_store.get("session:one", "submit:one")

    assert recovered is not None
    assert recovered.status == "completed"
    assert recovered.result == {"ok": True, "interaction_id": "interaction:one"}
    assert not namespace.exists()


def test_claim_token_prevents_non_owner_finalization(tmp_path: Path) -> None:
    namespace = tmp_path / "jobs.sqlite"
    store = RpgForegroundSubmissionStore(namespace)
    claim = store.claim("session:one", "submit:one")

    assert store.complete(
        "session:one",
        "submit:one",
        "not-the-owner-token",
        {"ok": True},
    ) is False
    assert store.fail(
        "session:one",
        "submit:one",
        "not-the-owner-token",
        "not owner",
    ) is False
    current = store.get("session:one", "submit:one")

    assert claim.owner is True
    assert current is not None
    assert current.status == "claimed"
    assert current.result is None
    assert current.error is None
    assert not namespace.exists()


def test_provider_free_submission_store_is_an_in_process_test_double(tmp_path: Path) -> None:
    namespace = tmp_path / "foreground-submissions.sqlite"
    store = RpgForegroundSubmissionStore(namespace)

    claim = store.claim("session:test-double", "submission:test-double")

    assert claim.owner is True
    assert not hasattr(store, "_connect")
    assert not namespace.exists()
