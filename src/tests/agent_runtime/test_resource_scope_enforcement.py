from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime.broker_api import _request_within_resource_scopes
from app.agent_runtime.contracts import AgentRunSpec, ModelRef, ResourceScope


def _snapshot(scopes):
    return SimpleNamespace(
        spec=AgentRunSpec(
            task="scoped",
            model=ModelRef(provider_id="test", model_id="model"),
            external_capabilities=["github.read_repo"],
            resource_scopes=scopes,
        )
    )


def test_declared_external_scope_denies_other_repository() -> None:
    snapshot = _snapshot([
        ResourceScope(
            capability="github.read_repo",
            resource_type="repository",
            resource_id="autonomx/omnix",
        )
    ])
    assert _request_within_resource_scopes(
        snapshot,
        "github.read_repo",
        {"repository": "autonomx/omnix"},
    )
    assert not _request_within_resource_scopes(
        snapshot,
        "github.read_repo",
        {"repository": "someone/else"},
    )


def test_scope_constraints_are_also_enforced() -> None:
    snapshot = _snapshot([
        ResourceScope(
            capability="github.read_repo",
            resource_type="repository",
            resource_id="autonomx/omnix",
            constraints={"ref": "main"},
        )
    ])
    assert _request_within_resource_scopes(
        snapshot,
        "github.read_repo",
        {"repository": "autonomx/omnix", "ref": "main"},
    )
    assert not _request_within_resource_scopes(
        snapshot,
        "github.read_repo",
        {"repository": "autonomx/omnix", "ref": "dev"},
    )


def test_no_scope_for_capability_preserves_issued_capability_authority() -> None:
    assert _request_within_resource_scopes(
        _snapshot([]),
        "github.read_repo",
        {"repository": "autonomx/omnix"},
    )
