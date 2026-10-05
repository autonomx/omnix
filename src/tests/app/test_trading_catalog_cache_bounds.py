from app.trading import catalog


def _instrument(instrument_id: str):
    return catalog.INSTRUMENTS[0].model_copy(
        update={"instrument_id": instrument_id, "venue_symbol": instrument_id},
    )


def test_dynamic_catalog_cache_expires_and_is_invalidatable(monkeypatch) -> None:
    catalog.clear_dynamic_catalog_cache()
    monkeypatch.setattr(catalog, "DYNAMIC_CATALOG_TTL_SECONDS", 5.0)
    now = {"value": 10.0}
    monkeypatch.setattr(catalog.time, "monotonic", lambda: now["value"])

    instrument = _instrument("test:ephemeral:first")
    catalog.register_instrument(instrument)
    assert catalog.instrument_by_id(instrument.instrument_id) == instrument

    now["value"] = 16.0
    assert catalog.instrument_by_id(instrument.instrument_id) is None

    catalog.register_instrument(instrument)
    catalog.clear_dynamic_catalog_cache()
    assert catalog.instrument_by_id(instrument.instrument_id) is None


def test_dynamic_catalog_cache_evicts_oldest_when_at_capacity(monkeypatch) -> None:
    catalog.clear_dynamic_catalog_cache()
    monkeypatch.setattr(catalog, "MAX_DYNAMIC_CATALOG_ENTRIES", 1)
    monkeypatch.setattr(catalog, "DYNAMIC_CATALOG_TTL_SECONDS", 50.0)
    monkeypatch.setattr(catalog.time, "monotonic", lambda: 10.0)

    first = _instrument("test:capacity:first")
    second = _instrument("test:capacity:second")
    catalog.register_instrument(first)
    catalog.register_instrument(second)

    assert catalog.instrument_by_id(first.instrument_id) is None
    assert catalog.instrument_by_id(second.instrument_id) == second
    catalog.clear_dynamic_catalog_cache()
