"""A provider/model pair as settings and requests write it, parsed in one place.

Settings and browser Chat store a selectable model as ``llm:<provider>:<model>`` and a provider as
``llm:<provider>`` or ``<provider>``. Callers parse those here instead of splitting the strings themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.providers.catalog import provider_id_of

if TYPE_CHECKING:
    from app.settings.profile_models import SettingsProfile

_PREFIX = "llm:"


def _qualified(value: Any) -> tuple[str, str] | None:
    """``(provider, model)`` of an ``llm:<provider>:<model>`` reference; None for any other text."""
    text = str(value or "").strip()
    if text[: len(_PREFIX)].casefold() != _PREFIX:
        return None
    parts = text.split(":", 2)
    return (parts[1].strip(), parts[2].strip()) if len(parts) == 3 else ("", "")


def model_name_of(value: Any) -> str:
    """The model name a provider expects.

    ``<model>`` of an ``llm:<provider>:<model>`` reference, the text itself for a bare name, and "" for an
    ``llm:`` text that names no model.
    """
    qualified = _qualified(value)
    return qualified[1] if qualified is not None else str(value or "").strip()


def model_provider_of(value: Any) -> str:
    """The provider an ``llm:<provider>:<model>`` reference names; "" for a bare model name."""
    qualified = _qualified(value)
    return provider_id_of(qualified[0]) if qualified is not None else ""


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """A provider id (no ``llm:`` prefix) and the model name it expects ("" leaves the provider's own choice)."""

    provider: str = ""
    model: str = ""
    model_provider: str = ""  # the provider the model reference named; "" for a bare name

    @classmethod
    def parse(cls, provider_id: Any, model_id: Any) -> ModelRoute:
        return cls(provider_id_of(provider_id), model_name_of(model_id), model_provider_of(model_id))

    @property
    def matched(self) -> bool:
        """The model belongs to the provider: it named no provider, or the same one."""
        return not self.model_provider or self.model_provider == self.provider

    @property
    def own_model(self) -> str:
        """The model, or "" when it names another provider (a model belongs to its provider)."""
        return self.model if self.matched else ""

    def model_led(self) -> ModelRoute:
        """The route a selected model implies: a model that names its provider moves the route there."""
        if self.model_provider and self.model:
            return ModelRoute(self.model_provider, self.model, self.model_provider)
        return self


def task_override_route(profile: SettingsProfile, key: str) -> ModelRoute:
    """The provider and model a Settings routing override names for ``key``; an empty route when it names none."""
    from app.settings.effective_defaults import task_override

    return ModelRoute.parse(*task_override(profile, key))


def effective_model_route(profile: SettingsProfile, module: str, task: str) -> ModelRoute:
    """Settings' ``effective_llm_route`` for a module's task, parsed: the provider id and the model name it expects."""
    from app.settings.effective_defaults import effective_llm_route

    return ModelRoute.parse(*effective_llm_route(profile, module, task))


__all__ = ["ModelRoute", "effective_model_route", "model_name_of", "model_provider_of", "task_override_route"]
