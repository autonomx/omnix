"""Chat reaches research through research.contracts (WP-8.2)."""
from __future__ import annotations

from importlib import import_module

import pytest

from app.research import contracts
from app.runtime.feature_catalog import load_feature


def test_every_entry_point_is_the_defining_modules_object() -> None:
    for name, module in contracts._ENTRY_POINTS.items():
        assert getattr(contracts, name) is getattr(import_module(f"app.research.{module}"), name)


def test_an_unknown_name_is_an_attribute_error() -> None:
    with pytest.raises(AttributeError):
        contracts.not_a_research_entry_point  # noqa: B018


def test_research_declares_its_chat_dependency() -> None:
    # The lint allows chat -> research.contracts only between declared dependents.
    assert "chat" in load_feature("research").depends_on
