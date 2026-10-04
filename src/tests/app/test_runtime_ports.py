"""Typed ports and FeatureModule contributions (ADR-0016, PA-1.3)."""
from __future__ import annotations

from typing import Protocol

from fastapi import FastAPI
import pytest

import app.gateway.feature_registry as feature_registry
from app.runtime import ports
from app.runtime.capabilities import RuntimeCapabilities
from app.runtime.config import RuntimeConfig
from app.runtime.features import FeatureModule
from app.security.permissions import FEATURE_DEFAULTS
from app.runtime.ports import (
    ContributionSpec, Port, PortBinding, PortBindingError, PortBindings, PortUnbound,
)


class Greeter(Protocol):
    def greet(self) -> str: ...


MANY = Port("test.greeters", Greeter, "many")
ONE_OR_NONE = Port("test.greeter", Greeter, "at_most_one")
EXACTLY_ONE = Port("test.clock", object, "exactly_one")


@pytest.fixture(autouse=True)
def clean_bindings():
    ports.reset_port_bindings_for_tests()
    yield
    ports.reset_port_bindings_for_tests()


def test_many_port_orders_implementations_by_priority_then_owner():
    bindings = PortBindings.build([
        PortBinding(MANY, "late", owner="alpha", priority=200),
        PortBinding(MANY, "beta", owner="beta", priority=100),
        PortBinding(MANY, "alpha", owner="alpha", priority=100),
    ])
    ports.install_port_bindings(bindings)
    assert ports.implementations(MANY) == ("alpha", "beta", "late")


def test_at_most_one_port_returns_none_when_absent_and_rejects_two():
    assert ports.optional(ONE_OR_NONE) is None
    with pytest.raises(PortBindingError, match="accepts one implementation"):
        PortBindings.build([
            PortBinding(ONE_OR_NONE, "a", owner="a"),
            PortBinding(ONE_OR_NONE, "b", owner="b"),
        ])


def test_exactly_one_port_is_bound_only_by_composition():
    with pytest.raises(ValueError, match="only the composition layer binds it"):
        ContributionSpec(EXACTLY_ONE, lambda _context: object())
    with pytest.raises(PortBindingError, match="cannot bind it"):
        PortBindings.build([PortBinding(EXACTLY_ONE, object(), owner="some-feature")])
    with pytest.raises(PortUnbound):
        PortBindings.build([], required=(EXACTLY_ONE,))
    with pytest.raises(PortUnbound):
        ports.required(EXACTLY_ONE)

    clock = object()
    ports.install_port_bindings(PortBindings.build([PortBinding(EXACTLY_ONE, clock)], required=(EXACTLY_ONE,)))
    assert ports.required(EXACTLY_ONE) is clock


def test_accessors_match_the_port_cardinality():
    with pytest.raises(TypeError):
        ports.optional(MANY)
    with pytest.raises(TypeError):
        ports.implementations(ONE_OR_NONE)
    with pytest.raises(TypeError):
        ports.required(ONE_OR_NONE)


def test_ports_compare_by_identity_not_name():
    twin = Port("test.greeters", Greeter, "many")
    ports.install_port_bindings(PortBindings.build([PortBinding(MANY, "bound", owner="a")]))
    assert ports.implementations(twin) == ()


def test_installing_bindings_replaces_the_previous_set():
    ports.install_port_bindings(PortBindings.build([PortBinding(ONE_OR_NONE, "first", owner="a")]))
    ports.install_port_bindings(PortBindings.build([]))
    assert ports.optional(ONE_OR_NONE) is None


def test_feature_module_accepts_only_contribution_specs():
    with pytest.raises(TypeError, match="ContributionSpec"):
        FeatureModule(id="sample", title="Sample", tier="app", contributions=("not a spec",))  # type: ignore[arg-type]


def test_composition_builds_contributions_from_the_feature_context(monkeypatch):
    seen = []

    class SampleGreeter:
        def greet(self) -> str:
            return "hello"

    def factory(context):
        seen.append(context.feature_id)
        return SampleGreeter()

    feature = FeatureModule(
        id="sample-feature",
        title="Sample feature",
        tier="app",
        contributions=(ContributionSpec(ONE_OR_NONE, factory),),
    )
    monkeypatch.setattr(feature_registry, "enabled_feature_ids", lambda _config: (feature.id,))
    monkeypatch.setattr(feature_registry, "load_feature", lambda _feature_id: feature)
    monkeypatch.setattr(feature_registry, "reset_repository_specs", lambda: None)
    monkeypatch.setattr(feature_registry, "install_repository_specs", lambda _specs: None)
    monkeypatch.setattr(feature_registry, "shared_repository_specs", lambda: ())
    monkeypatch.setitem(FEATURE_DEFAULTS, "sample_feature", ("chat:read", "chat:write"))
    gateway = FastAPI()
    gateway.state.runtime_config = RuntimeConfig()
    gateway.state.runtime_capabilities = RuntimeCapabilities.from_config(RuntimeConfig())
    gateway.state.runtime_services = None
    gateway.state.background_registry = None

    feature_registry._register_feature_modules(gateway)

    assert seen == ["sample-feature"]
    assert ports.optional(ONE_OR_NONE).greet() == "hello"
    assert gateway.state.port_bindings.owners() == {"test.greeter": 1}
