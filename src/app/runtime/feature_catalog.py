"""Lazy catalog for features migrated to the FeatureModule contract."""
from __future__ import annotations

from importlib import import_module

from .config import RuntimeConfig
from .features import FeatureModule

FEATURE_CATALOG: dict[str, str] = {
    "audiobook": "app.audiobook.feature:FEATURE",
    "assistant-tools": "app.assistant_tools.feature:FEATURE",
    "agent-runtime": "app.agent_runtime.feature:FEATURE",
    "chat": "app.chat.feature:FEATURE",
    "image": "app.image.feature:FEATURE",
    "voice": "app.voice.feature:FEATURE",
    "research": "app.research.feature:FEATURE",
    "story": "app.story.feature:FEATURE",
    "rpg": "app.rpg.feature:FEATURE",
    "trading": "app.trading.feature:FEATURE",
}


def load_feature(feature_id: str) -> FeatureModule:
    target = FEATURE_CATALOG[feature_id]
    module_name, attribute = target.split(":", 1)
    feature = getattr(import_module(module_name), attribute)
    if not isinstance(feature, FeatureModule):
        raise TypeError(f"{target} did not expose a FeatureModule")
    if feature.id != feature_id:
        raise ValueError(f"Feature catalog id mismatch: {feature_id} != {feature.id}")
    return feature


def enabled_feature_ids(config: RuntimeConfig) -> tuple[str, ...]:
    requested = set(config.enabled_features)
    disabled = set(config.disabled_features)
    unknown = (requested - {"all"} - set(FEATURE_CATALOG)) | (disabled - set(FEATURE_CATALOG))
    if unknown:
        raise ValueError(f"Unknown feature ids: {sorted(unknown)}")
    selected = set(FEATURE_CATALOG) if "all" in requested else requested
    selected -= disabled
    for feature_id in tuple(selected):
        feature = load_feature(feature_id)
        missing = set(feature.depends_on) - selected
        if missing:
            raise ValueError(
                f"Feature {feature_id} requires disabled features: {sorted(missing)}"
            )
    return tuple(feature_id for feature_id in FEATURE_CATALOG if feature_id in selected)
