"""The protected store under concurrent use and corruption (TVP-1.2 alert webhooks)."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from app.security import provider_secret_store as store

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the protected store needs DPAPI")

HOOK = "https://hooks.example.com/services/T/B/token"
SRC = str(Path(__file__).resolve().parents[2])


@pytest.fixture()
def secrets_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "secrets.dpapi"
    monkeypatch.setenv("OMNIX_PROVIDER_SECRETS_PATH", str(path))
    return path


def test_reads_never_miss_an_existing_webhook_while_threads_write(secrets_path) -> None:
    store.save_alert_webhook("w/seed/0", HOOK, "seed")
    problems: list[str] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            try:
                if store.load_alert_webhook("w/seed/0") != {"url": HOOK, "secret": "seed"}:
                    problems.append("missing")
            except Exception as exc:  # a read failure must be loud, but must not happen here
                problems.append(repr(exc))

    def writer(index: int) -> None:
        for step in range(15):
            store.save_alert_webhook(f"w/a{index}/{step}", HOOK, str(step))

    readers = [threading.Thread(target=reader) for _ in range(3)]
    writers = [threading.Thread(target=writer, args=(index,)) for index in range(3)]
    for thread in readers + writers:
        thread.start()
    for thread in writers:
        thread.join()
    stop.set()
    for thread in readers:
        thread.join()
    assert problems == []
    assert all(store.load_alert_webhook(f"w/a{index}/{step}") is not None for index in range(3) for step in range(15))


_WRITER = """
import sys
from app.security.provider_secret_store import save_alert_webhook
errors = 0
for step in range(20):
    try:
        save_alert_webhook(f"w/p{sys.argv[1]}/{step}", "https://hooks.example.com/x", str(step))
    except Exception as exc:
        errors += 1
        print(repr(exc))
print("errors", errors)
"""

_READER = """
from app.security.provider_secret_store import load_alert_webhook
problems = 0
for _ in range(300):
    try:
        if load_alert_webhook("w/seed/0") is None:
            problems += 1
    except Exception as exc:
        problems += 1
        print(repr(exc))
print("problems", problems)
"""


def test_processes_neither_fail_writes_nor_read_an_empty_store(secrets_path) -> None:
    store.save_alert_webhook("w/seed/0", HOOK, "seed")
    environment = {**os.environ, "OMNIX_PROVIDER_SECRETS_PATH": str(secrets_path), "PYTHONPATH": SRC}
    processes = [
        subprocess.Popen([sys.executable, "-c", textwrap.dedent(_WRITER), str(index)], env=environment, stdout=subprocess.PIPE, text=True)
        for index in range(2)
    ] + [
        subprocess.Popen([sys.executable, "-c", textwrap.dedent(_READER)], env=environment, stdout=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    outputs = [process.communicate(timeout=180)[0] for process in processes]
    assert all(process.returncode == 0 for process in processes), outputs
    assert [output.strip().splitlines()[-1] for output in outputs] == ["errors 0", "errors 0", "problems 0", "problems 0"], outputs
    assert all(store.load_alert_webhook(f"w/p{index}/{step}") is not None for index in range(2) for step in range(20))


def test_an_undecryptable_store_is_never_overwritten(secrets_path) -> None:
    store.save_trading_provider_secrets("coinmarketcap", {"api_key": "precious"})
    secrets_path.write_bytes(b"not a dpapi blob")
    for write in (
        lambda: store.save_alert_webhook("w/a/1", HOOK, "s"),
        lambda: store.delete_alert_webhooks(prefix="w/"),
        lambda: store.save_trading_provider_secrets("coinmarketcap", {"api_key": "other"}),
        lambda: store.save_research_provider_secret("brave", "k"),
        lambda: store.save_provider_secrets({"api_keys": {"openrouter": "k"}}),
    ):
        with pytest.raises(store.ProviderSecretStoreUnavailable):
            write()
        assert secrets_path.read_bytes() == b"not a dpapi blob"
    with pytest.raises(store.ProviderSecretStoreUnavailable):
        store.load_alert_webhook("w/a/1")


def test_a_replace_blocked_by_another_handle_is_retried(secrets_path, monkeypatch) -> None:
    store.save_alert_webhook("w/a/1", HOOK, "s")
    real_replace = os.replace
    attempts: list[int] = []

    def flaky_replace(source, target):
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError(13, "in use")
        return real_replace(source, target)

    monkeypatch.setattr(store.os, "replace", flaky_replace)
    store.save_alert_webhook("w/a/2", HOOK, "t")
    assert len(attempts) == 3
    assert store.load_alert_webhook("w/a/2") == {"url": HOOK, "secret": "t"}
