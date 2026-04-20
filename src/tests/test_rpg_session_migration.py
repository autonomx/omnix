import shutil
from pathlib import Path


def test_legacy_session_migration(tmp_path, monkeypatch):
    """
    Ensures legacy data/rpg_sessions is migrated correctly.
    """

    # Setup fake project root
    root = tmp_path
    legacy = root / "data" / "rpg_sessions"
    new = root / "resources" / "data" / "rpg_sessions"

    legacy.mkdir(parents=True)
    (legacy / "test_session.json").write_text('{"ok": true}')

    # Monkeypatch cwd so module uses this temp root
    monkeypatch.chdir(root)

    # Import triggers migration
    import importlib
    mod = importlib.import_module("app.rpg.session.durable_store")
    importlib.reload(mod)

    # Assertions
    assert not legacy.exists(), "Legacy dir should be moved"
    assert new.exists(), "New dir should exist"
    assert (new / "test_session.json").exists(), "File should be preserved"