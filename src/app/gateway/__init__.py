"""Gateway exports; feature composition belongs to the application factory."""

from typing import Any

__all__ = ["app", "create_gateway_app"]


def _install_required_rpg_turn_hooks():
    from .runtime_hooks import _install_required_rpg_turn_hooks as install

    install()


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .main import app, create_gateway_app

        return {"app": app, "create_gateway_app": create_gateway_app}[name]
    raise AttributeError(name)
