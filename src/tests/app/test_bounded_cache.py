from app.caching import bounded_cache
from app.caching.bounded_cache import bounded_lru_cache


def test_bounded_lru_cache_expires_and_can_be_invalidated(monkeypatch) -> None:
    now = 100.0
    calls = 0
    expired: list[int] = []
    monkeypatch.setattr(bounded_cache, "_cache_now", lambda: now)

    @bounded_lru_cache(max_entries=2, ttl_seconds=10, on_evict=expired.append)
    def compute(value: int) -> int:
        nonlocal calls
        calls += 1
        return value * 2

    assert compute(3) == 6
    assert compute(3) == 6
    assert calls == 1
    compute(4)
    compute(5)
    assert compute.cache_info().currsize == 2

    now += 11
    assert compute(3) == 6
    assert calls == 4
    assert expired == [6, 8, 10]
    compute.cache_clear()
    assert compute.cache_info().currsize == 0
    assert compute(3) == 6
    assert calls == 5
