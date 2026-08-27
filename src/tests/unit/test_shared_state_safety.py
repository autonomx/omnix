from __future__ import annotations

import threading
import time

from app import shared


def test_default_settings_are_deep_copied(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(shared, "_settings_load_override", None)
    monkeypatch.setattr(shared, "SETTINGS_FILE", str(tmp_path / "missing-settings.json"))

    first = shared.load_settings()
    first["lmstudio"]["base_url"] = "http://mutated.invalid"
    first["image"]["flux_klein"]["width"] = 1

    second = shared.load_settings()

    assert second["lmstudio"]["base_url"] == "http://localhost:1234"
    assert second["image"]["flux_klein"]["width"] == 768
    assert shared.DEFAULT_SETTINGS["lmstudio"]["base_url"] == "http://localhost:1234"
    assert shared.DEFAULT_SETTINGS["image"]["flux_klein"]["width"] == 768


def test_update_sessions_serializes_read_modify_write(monkeypatch) -> None:
    stored: dict[str, object] = {}
    storage_lock = threading.Lock()

    def load() -> dict[str, object]:
        with storage_lock:
            return dict(stored)

    def save(value: dict[str, object]) -> None:
        with storage_lock:
            stored.clear()
            stored.update(value)

    monkeypatch.setattr(shared, "load_sessions", load)
    monkeypatch.setattr(shared, "save_sessions", save)

    def add_first(current: dict[str, object]) -> None:
        time.sleep(0.03)
        current["first"] = {"messages": []}

    def add_second(current: dict[str, object]) -> None:
        current["second"] = {"messages": []}

    first = threading.Thread(target=shared.update_sessions, args=(add_first,))
    second = threading.Thread(target=shared.update_sessions, args=(add_second,))
    first.start()
    second.start()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert set(stored) == {"first", "second"}
