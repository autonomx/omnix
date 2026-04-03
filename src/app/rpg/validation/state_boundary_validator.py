"""PHASE 5.5 — State Boundary Validation.

Validation helpers for deterministic state serialization and side-effect isolation.
"""

from __future__ import annotations

from typing import Any, Dict


class StateBoundaryValidator:
    """Validate subsystem state boundaries and replay-safe behavior."""

    def validate_serializable(self, system: Any) -> Dict[str, Any]:
        result = {
            "has_serialize_state": hasattr(system, "serialize_state"),
            "has_deserialize_state": hasattr(system, "deserialize_state"),
            "ok": False,
        }
        result["ok"] = result["has_serialize_state"] and result["has_deserialize_state"]
        return result

    def validate_roundtrip(self, system: Any) -> Dict[str, Any]:
        if not hasattr(system, "serialize_state") or not hasattr(system, "deserialize_state"):
            return {"ok": False, "reason": "missing serialize_state/deserialize_state"}

        state = system.serialize_state()
        system.deserialize_state(state)
        state2 = system.serialize_state()

        return {
            "ok": state == state2,
            "state_before": state,
            "state_after": state2,
        }

    def validate_effect_blocking(self, effect_manager: Any) -> Dict[str, Any]:
        try:
            effect_manager.check("network", {"url": "https://example.com"})
            return {"ok": False, "reason": "network unexpectedly allowed"}
        except RuntimeError:
            return {"ok": True}

    def validate_llm_replay_safety(self, gateway: Any) -> Dict[str, Any]:
        """Validate that LLM gateway fails on unrecorded replay calls."""
        try:
            gateway.set_mode("replay")
            gateway.call("complete", "unrecorded prompt", context={"test": True})
            return {"ok": False, "reason": "unrecorded replay call unexpectedly succeeded"}
        except (KeyError, RuntimeError):
            return {"ok": True}
        except Exception as exc:
            return {
                "ok": False,
                "reason": f"unexpected exception type during replay validation: {type(exc).__name__}: {exc}",
            }

    def validate_tool_runtime_replay_safety(self, gateway: Any) -> Dict[str, Any]:
        """Validate that tool/runtime gateway fails on unrecorded replay calls."""
        try:
            gateway.set_mode("replay")
            gateway.call("unrecorded_tool", {"x": 1}, context={"test": True})
            return {"ok": False, "reason": "unrecorded replay tool call unexpectedly succeeded"}
        except (KeyError, RuntimeError):
            return {"ok": True}
        except Exception as exc:
            return {
                "ok": False,
                "reason": f"unexpected exception type during tool replay validation: {type(exc).__name__}: {exc}",
            }

    def validate_host_runtime_replay_safety(self, gateway: Any) -> Dict[str, Any]:
        """Validate that host/runtime gateway fails on unrecorded replay calls."""
        try:
            gateway.set_mode("replay")
            gateway.call("unrecorded_op", {"x": 1}, context={"test": True})
            return {"ok": False, "reason": "unrecorded replay host call unexpectedly succeeded"}
        except (KeyError, RuntimeError):
            return {"ok": True}
        except Exception as exc:
            return {
                "ok": False,
                "reason": f"unexpected exception type during host replay validation: {type(exc).__name__}: {exc}",
            }
