"""Process-scoped feature hook registry composed at startup."""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class RuntimeHookSpec:
    name: str
    handler: Callable[..., Any]

    def __post_init__(self) -> None:
        if not self.name.strip() or self.name != self.name.strip():
            raise ValueError("runtime hook name must be normalized")


_LOCK = RLock()
_HOOKS: dict[str, Callable[..., Any]] = {}


def install_runtime_hooks(specs: tuple[RuntimeHookSpec, ...]) -> None:
    with _LOCK:
        for spec in specs:
            existing = _HOOKS.get(spec.name)
            if existing is not None and existing is not spec.handler:
                raise ValueError(f"duplicate runtime hook: {spec.name}")
            _HOOKS[spec.name] = spec.handler


def invoke_runtime_hook(name: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    with _LOCK:
        handler = _HOOKS.get(name)
    if handler is None:
        return default
    return handler(*args, **kwargs)


def reset_runtime_hooks_for_tests() -> None:
    with _LOCK:
        _HOOKS.clear()
