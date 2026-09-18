from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from app.trading.providers.http_runtime import ProviderHttpRuntime


class _SlowSession:
    def __init__(self) -> None:
        self.calls = 0
        self.lock = threading.Lock()

    def request(self, method, url, **kwargs):
        with self.lock:
            self.calls += 1
        time.sleep(0.05)
        return SimpleNamespace(
            status_code=200,
            headers={},
            raise_for_status=lambda: None,
        )


def test_identical_provider_requests_are_single_flight() -> None:
    session = _SlowSession()
    runtime = ProviderHttpRuntime(
        "test",
        session=session,
        max_attempts=1,
        max_concurrency=4,
    )
    barrier = threading.Barrier(3)
    results = []
    errors = []

    def worker() -> None:
        try:
            barrier.wait()
            results.append(
                runtime.get_coalesced(
                    "same-request",
                    "https://example.test/data",
                )
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=2)

    assert errors == []
    assert len(results) == 2
    assert session.calls == 1
    assert results[0] is results[1]
