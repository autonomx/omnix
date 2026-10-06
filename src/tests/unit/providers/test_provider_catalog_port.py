"""Feature provider lists reach the facade through PROVIDER_CATALOGS (ADR-0016, PA-1.1)."""
from __future__ import annotations

import pytest

from app.providers.facade import PROVIDER_CATALOGS, ProviderFacade
from app.runtime.ports import PortBinding, PortBindings, install_port_bindings, reset_port_bindings_for_tests


class _Catalog:
    def __init__(self, family: str, keys: list[str]) -> None:
        self.family = family
        self._keys = keys

    def list_providers(self):
        return [{"key": key, "label": key} for key in self._keys]


@pytest.fixture(autouse=True)
def clean_bindings():
    reset_port_bindings_for_tests()
    yield
    reset_port_bindings_for_tests()


def test_facade_lists_each_family_from_its_contributed_catalogs():
    install_port_bindings(PortBindings.build([
        PortBinding(PROVIDER_CATALOGS, _Catalog("image", ["mock"]), owner="image"),
        PortBinding(PROVIDER_CATALOGS, _Catalog("rpg_visual", ["disabled"]), owner="rpg"),
    ]))
    facade = ProviderFacade()
    assert [info["key"] for info in facade._list_image()] == ["mock"]
    assert [info["key"] for info in facade._list_visual()] == ["disabled"]


def test_without_contributing_features_the_families_are_empty():
    facade = ProviderFacade()
    assert facade._list_image() == []
    assert facade._list_visual() == []
