import pytest

from app.runtime import hooks


def test_runtime_hook_registry_publishes_immutable_bounded_snapshots() -> None:
    hooks.reset_runtime_hooks_for_tests()
    expected = object()

    def handler(value):
        return value

    spec = hooks.RuntimeHookSpec(name="test.handler", handler=handler)

    hooks.install_runtime_hooks((spec,))
    assert hooks.invoke_runtime_hook("test.handler", expected) is expected
    with pytest.raises(TypeError):
        hooks._HOOKS["illegal"] = handler
    hooks.reset_runtime_hooks_for_tests()
    assert hooks.invoke_runtime_hook("test.handler", expected, default=None) is None
