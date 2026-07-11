"""Stable facade over the generated RPG runtime foundation.

The legacy module remains a deterministic compatibility dependency, while final
visible response selection gives canonical validated runtime payloads first
ownership.
"""
from __future__ import annotations

from . import runtime_part01_legacy as _legacy

for _name in _legacy.__all__:
    globals()[_name] = getattr(_legacy, _name)

_legacy_select_final_visible_presentation = (
    _legacy._select_final_visible_presentation
)


def _select_final_visible_presentation(
    final_result,
    *,
    runtime_narration_payload,
    prior_narration,
    prior_npc,
    prior_llm_called,
):
    final_result = _safe_dict(final_result)
    runtime_narration_payload = _safe_dict(runtime_narration_payload)
    canonical_text = _safe_str(runtime_narration_payload.get("narration")).strip()
    if (
        runtime_narration_payload.get("canonical_response_source")
        == "rpg_response_generator_v1"
        and canonical_text
    ):
        return {
            "source": "canonical_runtime_response",
            "narration": canonical_text,
            "npc": _safe_dict(runtime_narration_payload.get("npc")),
            "llm_called": (
                _safe_str(runtime_narration_payload.get("source"))
                == "provider_runtime_narration"
            ),
            "runtime_payload_source": _safe_str(
                runtime_narration_payload.get("source")
            ),
        }
    return _legacy_select_final_visible_presentation(
        final_result,
        runtime_narration_payload=runtime_narration_payload,
        prior_narration=prior_narration,
        prior_npc=prior_npc,
        prior_llm_called=prior_llm_called,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
