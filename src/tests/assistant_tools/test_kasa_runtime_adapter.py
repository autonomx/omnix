from __future__ import annotations

from dataclasses import replace

from app.platform.assistant_tools.config_store import (
    AssistantToolConfigRecord,
    AssistantToolsConfigPayload,
    default_assistant_tools_config,
)
from types import MappingProxyType

from app.platform.assistant_tools import executor
from app.capabilities.executor import CapabilityGrant, execute_capability
from app.platform.assistant_tools.kasa_adapter import KasaDeviceRecord, run_kasa_tool_request
from app.platform.assistant_tools.models import AssistantToolRequest
import pytest

# Uses the PostgreSQL-backed runtime; runs in the test-postgres job.
pytestmark = pytest.mark.postgres


class FakeKasaAdapter:
    def __init__(self, *, initial_on: bool = False, verify_on: bool | None = None) -> None:
        self.device = KasaDeviceRecord(
            alias="Desk Plug",
            host="192.168.1.42",
            model="KP115",
            device_id="device-1",
            is_on=initial_on,
            rssi=-44,
        )
        self.verify_on = verify_on
        self.set_calls: list[tuple[str, bool]] = []

    def discover_devices(self) -> list[KasaDeviceRecord]:
        return [self.device]

    def get_state(self, *, target: str = "") -> KasaDeviceRecord:
        assert target in {"", "Desk Plug", "desk plug"}
        return self.device

    def set_state(self, *, target: str = "", on: bool):
        self.set_calls.append((target, on))
        after_on = on if self.verify_on is None else self.verify_on
        return self.device, replace(self.device, is_on=after_on)


def _connected_kasa_config() -> AssistantToolsConfigPayload:
    defaults = default_assistant_tools_config()
    return AssistantToolsConfigPayload(
        tools=[
            AssistantToolConfigRecord(
                tool_id=tool.tool_id,
                enabled=tool.tool_id == "kasa",
                connection_status="connected" if tool.tool_id == "kasa" else "not_configured",
                actions=tool.actions,
            )
            for tool in defaults.tools
        ]
    )


def test_kasa_discovery_and_state_reads_do_not_change_device_state() -> None:
    adapter = FakeKasaAdapter(initial_on=True)

    discovered = run_kasa_tool_request(
        AssistantToolRequest(tool_id="kasa", action_id="kasa.discover_devices"),
        adapter,
    )
    state = run_kasa_tool_request(
        AssistantToolRequest(
            tool_id="kasa",
            action_id="kasa.get_state",
            input={"target": "Desk Plug"},
        ),
        adapter,
    )

    assert discovered.error is None
    assert discovered.state_changed is False
    assert discovered.output["devices"][0]["model"] == "KP115"
    assert state.result_summary == "Desk Plug is on."
    assert state.output["device"]["is_on"] is True
    assert adapter.set_calls == []


def test_kasa_write_adapter_reports_verified_before_and_after_state() -> None:
    adapter = FakeKasaAdapter(initial_on=False)

    result = run_kasa_tool_request(
        AssistantToolRequest(
            tool_id="kasa",
            action_id="kasa.turn_on",
            input={"target": "Desk Plug"},
        ),
        adapter,
    )

    assert result.error is None
    assert result.state_changed is True
    assert result.output["verified"] is True
    assert result.output["before"]["is_on"] is False
    assert result.output["after"]["is_on"] is True
    assert adapter.set_calls == [("Desk Plug", True)]


def test_kasa_write_requires_approval_before_bridge_dispatch(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.platform.assistant_tools.gate.load_assistant_tools_config",
        _connected_kasa_config,
    )
    calls: list[AssistantToolRequest] = []

    def fake_run(request: AssistantToolRequest):
        calls.append(request)
        return run_kasa_tool_request(request, FakeKasaAdapter(initial_on=False))

    monkeypatch.setattr(executor, "ADAPTERS", MappingProxyType({**executor.ADAPTERS, "kasa": fake_run}))

    blocked = execute_capability(
        CapabilityGrant("chat", "chat:1"),
        AssistantToolRequest(
            tool_id="kasa",
            action_id="kasa.turn_on",
            session_id="chat:1",
            input={"target": "Desk Plug"},
        ),
        user_request="Turn on the desk plug",
    )
    approved = execute_capability(
        CapabilityGrant("chat", "chat:1", approved_by="user:local"),
        AssistantToolRequest(
            tool_id="kasa",
            action_id="kasa.turn_on",
            session_id="chat:1",
            input={"target": "Desk Plug"},
        ),
        user_request="Confirm",
    )

    assert blocked.approval_decision.approval_required is True
    assert blocked.execution_result.error == "approval_required"
    assert len(calls) == 1
    assert calls[0].session_id == "chat:1"
    assert calls[0].action_id == "kasa.turn_on"
    assert approved.execution_result.error is None
    assert approved.execution_result.output["after"]["is_on"] is True


def test_kasa_adapter_surfaces_verification_failure_without_state_change() -> None:
    class FailingAdapter(FakeKasaAdapter):
        def set_state(self, *, target: str = "", on: bool):
            raise RuntimeError("Kasa state verification failed")

    result = run_kasa_tool_request(
        AssistantToolRequest(
            tool_id="kasa",
            action_id="kasa.turn_off",
            input={"target": "Desk Plug"},
        ),
        FailingAdapter(initial_on=True),
    )

    assert result.error == "Kasa state verification failed"
    assert result.state_changed is False
    assert result.result_summary == "Kasa action failed."
