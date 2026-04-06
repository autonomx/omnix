"""Phase 22 — UX / presentation / production polish.

UX cleanup, dialogue polish, streaming, speaker/emotion, encounter/map/quest UI,
accessibility, audio integration, QA, release candidate polish.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))

def _sf(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

def _ss(v: Any, d: str = "") -> str:
    return str(v) if v is not None else d

# Constants
MAX_DIALOGUE_HISTORY = 50
MAX_NOTIFICATIONS = 20
EMOTION_TYPES = ("neutral", "happy", "sad", "angry", "fearful", "surprised",
                 "disgusted", "contemptuous")
ACCESSIBILITY_MODES = ("standard", "high_contrast", "large_text", "screen_reader")

# ---------------------------------------------------------------------------
# 22.0 — UX architecture cleanup
# ---------------------------------------------------------------------------

@dataclass
class UXConfig:
    theme: str = "default"
    font_size: str = "medium"
    accessibility_mode: str = "standard"
    show_tooltips: bool = True
    animation_speed: float = 1.0
    audio_enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "theme": self.theme, "font_size": self.font_size,
            "accessibility_mode": self.accessibility_mode,
            "show_tooltips": self.show_tooltips,
            "animation_speed": self.animation_speed,
            "audio_enabled": self.audio_enabled,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UXConfig":
        return cls(
            theme=_ss(d.get("theme"), "default"),
            font_size=_ss(d.get("font_size"), "medium"),
            accessibility_mode=_ss(d.get("accessibility_mode"), "standard"),
            show_tooltips=bool(d.get("show_tooltips", True)),
            animation_speed=_clamp(_sf(d.get("animation_speed"), 1.0), 0.1, 3.0),
            audio_enabled=bool(d.get("audio_enabled", True)),
        )


@dataclass
class UXState:
    config: UXConfig = field(default_factory=UXConfig)
    active_panel: str = "dialogue"
    notifications: List[Dict[str, Any]] = field(default_factory=list)
    dialogue_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "active_panel": self.active_panel,
            "notifications": list(self.notifications),
            "dialogue_history": list(self.dialogue_history),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UXState":
        return cls(
            config=UXConfig.from_dict(d.get("config") or {}),
            active_panel=_ss(d.get("active_panel"), "dialogue"),
            notifications=list(d.get("notifications") or []),
            dialogue_history=list(d.get("dialogue_history") or []),
        )


# ---------------------------------------------------------------------------
# 22.1 — Dialogue UX polish
# ---------------------------------------------------------------------------

class DialogueUXPolish:
    @staticmethod
    def format_dialogue_turn(speaker: str, text: str,
                             emotion: str = "neutral",
                             is_player: bool = False) -> Dict[str, Any]:
        return {
            "speaker": speaker, "text": text,
            "emotion": emotion if emotion in EMOTION_TYPES else "neutral",
            "is_player": is_player,
            "display_class": "player-turn" if is_player else "npc-turn",
        }

    @staticmethod
    def add_to_history(state: UXState, turn: Dict[str, Any]) -> None:
        state.dialogue_history.append(turn)
        if len(state.dialogue_history) > MAX_DIALOGUE_HISTORY:
            state.dialogue_history = state.dialogue_history[-MAX_DIALOGUE_HISTORY:]


# ---------------------------------------------------------------------------
# 22.2 — Streaming / interruption UX polish
# ---------------------------------------------------------------------------

class StreamingUXManager:
    @staticmethod
    def create_streaming_placeholder(speaker: str) -> Dict[str, Any]:
        return {
            "speaker": speaker, "text": "", "streaming": True,
            "complete": False,
        }

    @staticmethod
    def update_streaming_text(placeholder: Dict[str, Any],
                              chunk: str) -> Dict[str, Any]:
        placeholder["text"] = placeholder.get("text", "") + chunk
        return placeholder

    @staticmethod
    def finalize_streaming(placeholder: Dict[str, Any]) -> Dict[str, Any]:
        placeholder["streaming"] = False
        placeholder["complete"] = True
        return placeholder


# ---------------------------------------------------------------------------
# 22.3 — Speaker / emotion / style presentation polish
# ---------------------------------------------------------------------------

class EmotionPresenter:
    EMOTION_ICONS = {
        "neutral": "😐", "happy": "😊", "sad": "😢", "angry": "😠",
        "fearful": "😨", "surprised": "😲", "disgusted": "🤢",
        "contemptuous": "😤",
    }

    @classmethod
    def get_emotion_display(cls, emotion: str) -> Dict[str, Any]:
        return {
            "emotion": emotion,
            "icon": cls.EMOTION_ICONS.get(emotion, "😐"),
            "css_class": f"emotion-{emotion}",
        }

    @staticmethod
    def get_speaker_style(speaker_id: str,
                          is_player: bool = False) -> Dict[str, Any]:
        if is_player:
            return {"color": "#4a9eff", "alignment": "right", "bold": True}
        return {"color": "#cccccc", "alignment": "left", "bold": False}


# ---------------------------------------------------------------------------
# 22.4 — Encounter / map / quest UI polish
# ---------------------------------------------------------------------------

class GameUIPresenter:
    @staticmethod
    def present_encounter_overlay(encounter_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "panel_type": "encounter",
            "visible": bool(encounter_data),
            "mode": encounter_data.get("mode", "combat"),
            "round": encounter_data.get("round", 0),
            "participants": encounter_data.get("participants", []),
        }

    @staticmethod
    def present_map_overlay(map_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "panel_type": "map",
            "visible": bool(map_data),
            "current_node": map_data.get("current_node", ""),
            "available_destinations": map_data.get("available_destinations", []),
        }

    @staticmethod
    def present_quest_tracker(quest_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "panel_type": "quest_tracker",
            "visible": bool(quest_data),
            "active_quests": quest_data.get("active_quests", []),
        }


# ---------------------------------------------------------------------------
# 22.5 — Accessibility / readability / controls
# ---------------------------------------------------------------------------

class AccessibilityManager:
    @staticmethod
    def apply_accessibility(config: UXConfig,
                            content: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(content)
        if config.accessibility_mode == "high_contrast":
            result["css_override"] = "high-contrast-theme"
        elif config.accessibility_mode == "large_text":
            result["css_override"] = "large-text-theme"
            result["font_scale"] = 1.5
        elif config.accessibility_mode == "screen_reader":
            result["aria_live"] = "polite"
            result["css_override"] = "screen-reader-theme"
        return result

    @staticmethod
    def get_supported_modes() -> List[str]:
        return list(ACCESSIBILITY_MODES)


# ---------------------------------------------------------------------------
# 22.6 — Audio / voice / subtitle integration polish
# ---------------------------------------------------------------------------

class AudioIntegration:
    @staticmethod
    def get_audio_cue(event_type: str) -> Dict[str, Any]:
        cues = {
            "attack": {"sound": "combat_hit", "volume": 0.8},
            "heal": {"sound": "magic_heal", "volume": 0.6},
            "dialogue_start": {"sound": "dialogue_open", "volume": 0.4},
            "quest_complete": {"sound": "quest_fanfare", "volume": 0.7},
            "discovery": {"sound": "discovery_chime", "volume": 0.5},
        }
        return cues.get(event_type, {"sound": "default", "volume": 0.5})

    @staticmethod
    def format_subtitle(speaker: str, text: str,
                        emotion: str = "neutral") -> Dict[str, Any]:
        return {
            "speaker": speaker, "text": text,
            "emotion_tag": f"[{emotion}]" if emotion != "neutral" else "",
            "display_duration_ms": max(2000, len(text) * 50),
        }


# ---------------------------------------------------------------------------
# 22.7 — Production QA / bug bash
# ---------------------------------------------------------------------------

class QAValidator:
    @staticmethod
    def validate_ux_state(state: UXState) -> List[str]:
        issues: List[str] = []
        if len(state.dialogue_history) > MAX_DIALOGUE_HISTORY:
            issues.append(f"dialogue_history exceeds max ({len(state.dialogue_history)} > {MAX_DIALOGUE_HISTORY})")
        if len(state.notifications) > MAX_NOTIFICATIONS:
            issues.append(f"notifications exceed max ({len(state.notifications)} > {MAX_NOTIFICATIONS})")
        if state.config.accessibility_mode not in ACCESSIBILITY_MODES:
            issues.append(f"invalid accessibility mode: {state.config.accessibility_mode}")
        return issues


# ---------------------------------------------------------------------------
# 22.8 — Release candidate polish pass
# ---------------------------------------------------------------------------

class UXDeterminismValidator:
    @staticmethod
    def validate_determinism(s1: UXState, s2: UXState) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def normalize_state(state: UXState) -> UXState:
        hist = list(state.dialogue_history)
        if len(hist) > MAX_DIALOGUE_HISTORY:
            hist = hist[-MAX_DIALOGUE_HISTORY:]
        notifs = list(state.notifications)
        if len(notifs) > MAX_NOTIFICATIONS:
            notifs = notifs[-MAX_NOTIFICATIONS:]
        return UXState(
            config=UXConfig.from_dict(state.config.to_dict()),
            active_panel=state.active_panel,
            notifications=notifs,
            dialogue_history=hist,
        )
