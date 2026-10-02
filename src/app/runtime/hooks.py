"""Process-scoped feature hook registry composed at startup."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from threading import RLock
from typing import Any, Callable, Mapping


@dataclass(frozen=True, slots=True)
class RuntimeHookSpec:
    name: str
    handler: Callable[..., Any]

    def __post_init__(self) -> None:
        if not self.name.strip() or self.name != self.name.strip():
            raise ValueError("runtime hook name must be normalized")


_LOCK = RLock()
_HOOKS: Mapping[str, Callable[..., Any]] = MappingProxyType({})
MAX_RUNTIME_HOOKS = 256


def install_runtime_hooks(specs: tuple[RuntimeHookSpec, ...]) -> None:
    global _HOOKS
    with _LOCK:
        hooks = dict(_HOOKS)
        for spec in specs:
            existing = hooks.get(spec.name)
            if existing is not None and existing is not spec.handler:
                raise ValueError(f"duplicate runtime hook: {spec.name}")
            hooks[spec.name] = spec.handler
        if len(hooks) > MAX_RUNTIME_HOOKS:
            raise ValueError("runtime hook capacity exceeded")
        _HOOKS = MappingProxyType(hooks)


def invoke_runtime_hook(name: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    with _LOCK:
        handler = _HOOKS.get(name)
    if handler is None:
        return default
    return handler(*args, **kwargs)


def reset_runtime_hooks_for_tests() -> None:
    global _HOOKS
    with _LOCK:
        _HOOKS = MappingProxyType({})
