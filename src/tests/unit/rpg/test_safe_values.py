"""The one definition of the RPG's tolerant readers keeps each replaced copy's behaviour (WP-8.6)."""
from __future__ import annotations

from types import MappingProxyType

from app.apps.rpg.safe_values import dict_copy, list_copy, mapping_copy, safe_dict, safe_list, safe_str


def test_safe_readers_return_the_value_itself_and_copies_return_a_new_container() -> None:
    state = {"a": 1}
    items = [1]
    assert safe_dict(state) is state and safe_list(items) is items
    assert dict_copy(state) == state and dict_copy(state) is not state
    assert list_copy(items) == items and list_copy(items) is not items
    assert mapping_copy(MappingProxyType(state)) == state


def test_other_types_become_empty_containers_or_text() -> None:
    assert safe_dict([("a", 1)]) == {} and dict_copy(None) == {} and mapping_copy("x") == {}
    assert safe_list((1,)) == [] and list_copy("ab") == []
    assert safe_str(None) == "" and safe_str(3) == "3" and safe_str("  kept  ") == "  kept  "
