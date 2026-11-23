"""Feature configuration loader: a feature's prefixed environment values, validated."""
from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ValidationError

from .env import env_prefixed


def load_feature_config(
    feature_id: str,
    config_model: type[BaseModel] | None,
    *,
    env: Mapping[str, str] | None = None,
) -> BaseModel | None:
    """Validate a feature's prefixed environment values without exposing values in errors."""
    if config_model is None:
        return None
    normalized_id = "".join(char if char.isalnum() else "_" for char in feature_id.upper())
    prefix = f"OMNIX_{normalized_id}_"
    raw = env_prefixed(prefix, env=env)
    values: dict[str, str] = {}
    field_names = {name.casefold(): name for name in config_model.model_fields}
    unknown: list[str] = []
    for variable, value in raw.items():
        suffix = variable[len(prefix):]
        field_name = field_names.get(suffix.casefold())
        if field_name is None:
            unknown.append(variable)
            continue
        values[field_name] = value
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"Unknown configuration variables for feature {feature_id}: {names}")
    try:
        return config_model.model_validate_strings(values)
    except ValidationError as exc:
        fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
        raise ValueError(
            f"Invalid configuration for feature {feature_id}: {', '.join(fields)}"
        ) from None
