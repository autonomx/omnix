from __future__ import annotations

from app.image.routes import models


def test_image_download_metadata_is_bounded_expiring_and_clearable(monkeypatch) -> None:
    now = 100.0
    monkeypatch.setattr(models, "_download_metadata_now", lambda: now)
    monkeypatch.setattr(models, "_MAX_PROVIDER_DOWNLOAD_ENTRIES", 2)
    monkeypatch.setattr(models, "_DOWNLOAD_TOTAL_TTL_SECONDS", 10.0)
    monkeypatch.setattr(models, "_DOWNLOAD_TOKEN_TTL_SECONDS", 5.0)
    models.clear_image_download_metadata()

    models._remember_download_total("one", 1)
    models._remember_download_total("two", 2)
    models._remember_download_total("three", 3)
    models._remember_download_token("three", "temporary-secret")
    assert list(models._DOWNLOAD_TOTALS) == ["two", "three"]
    assert models._DOWNLOAD_TOKENS["three"][0] == "temporary-secret"

    now += 6.0
    with models._DOWNLOAD_TOTALS_LOCK:
        models._prune_download_metadata_locked(now)
    assert "three" not in models._DOWNLOAD_TOKENS
    assert list(models._DOWNLOAD_TOTALS) == ["two", "three"]

    now += 5.0
    with models._DOWNLOAD_TOTALS_LOCK:
        models._prune_download_metadata_locked(now)
    assert models._DOWNLOAD_TOTALS == {}

    models._remember_download_token("four", "temporary-secret")
    models.clear_image_download_metadata()
    assert not models._DOWNLOAD_TOTALS
    assert not models._DOWNLOAD_TOKENS
