"""The portrait runtime caps its CUDA allocator: uncapped, cuDNN's workspace once ran FLOAT's load from host memory."""
from __future__ import annotations

import importlib
import sys
import types

import pytest


@pytest.fixture
def float_runtime(monkeypatch):
    """``services.portrait.float_runtime`` over a stand-in torch that records the allocator fraction."""
    fractions: list[float] = []
    torch = types.ModuleType("torch")
    nn = types.ModuleType("torch.nn")
    nn.Module = type("Module", (), {})
    functional = types.ModuleType("torch.nn.functional")
    nn.functional = functional
    torch.nn = nn
    torch.no_grad = lambda: (lambda function: function)
    torch.cuda = types.SimpleNamespace(
        get_device_properties=lambda index: types.SimpleNamespace(total_memory=24 * 2**30),
        set_per_process_memory_fraction=fractions.append,
    )
    for name, module in {"torch": torch, "torch.nn": nn, "torch.nn.functional": functional}.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "services.portrait.float_runtime", raising=False)
    module = importlib.import_module("services.portrait.float_runtime")
    yield module, fractions
    sys.modules.pop("services.portrait.float_runtime", None)


def test_the_allocator_is_capped_at_four_gb_by_default(float_runtime, monkeypatch) -> None:
    module, fractions = float_runtime
    monkeypatch.delenv("OMNIX_PORTRAIT_VRAM_CAP_MB", raising=False)

    assert module.cap_vram() == 4096
    assert fractions == [pytest.approx(4 / 24)]


def test_the_cap_is_configurable_and_never_past_the_card(float_runtime, monkeypatch) -> None:
    module, fractions = float_runtime
    monkeypatch.setenv("OMNIX_PORTRAIT_VRAM_CAP_MB", "6144")
    module.cap_vram()
    monkeypatch.setenv("OMNIX_PORTRAIT_VRAM_CAP_MB", "65536")
    module.cap_vram()

    assert fractions == [pytest.approx(6 / 24), 1.0]


def test_the_load_check_asks_for_the_capped_peak(monkeypatch) -> None:
    from services.portrait import portrait_server

    assert portrait_server.LOAD_VRAM_GB * 1024 >= 4096
    assert portrait_server.LOAD_COMMIT_BYTES >= 8 * 1024**3
