from __future__ import annotations
from app.assistant_tools.home_adapter import run_home_tool_request
from app.assistant_tools.kasa_adapter import KasaDeviceRecord
from app.assistant_tools.models import AssistantToolRequest

class FakeHomeAdapter:
    def discover_devices(self):
        return [KasaDeviceRecord(alias="Desk", host="1.2.3.4", model="P", device_id="d1", is_on=True)]
    def get_state(self, *, target=""):
        return self.discover_devices()[0]
    def set_state(self, *, target="", on: bool):
        before = self.discover_devices()[0]
        after = KasaDeviceRecord(alias=before.alias, host=before.host, model=before.model, device_id=before.device_id, is_on=on)
        return before, after

def test_semantic_home_adapter_hides_vendor_action_names() -> None:
    result = run_home_tool_request(AssistantToolRequest(tool_id="home", action_id="home.set_state", input={"target": "Desk", "on": False}), FakeHomeAdapter())
    assert result.error is None
    assert result.output["after"]["provider"] == "kasa"
    assert result.output["after"]["on"] is False
