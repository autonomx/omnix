"""Admission to the local GPU for one language-model call.

A call to a provider that runs on this machine's GPU (catalog ``LOCAL_DEVICE``) holds an
``llm-local`` device permit for its whole duration, so batch work (world genesis, dubbing
translation, memory readings) queues behind interactive chat instead of contending for VRAM.
A hosted provider needs no permit. Which providers are local is the catalog's decision, not
the caller's: callers pass the provider (an id, ``llm:`` prefix allowed, or an instance).
"""
from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import Any

from app.persistence.device_permits import DevicePermitLease, PermitPriority, device_permit_slot
from app.providers.catalog import LOCAL_DEVICE, provider_supports


def llm_admission(
    provider: Any,
    *,
    priority: PermitPriority = "batch",
    timeout_seconds: float = 30.0,
) -> AbstractContextManager[DevicePermitLease | None]:
    """Hold the local-GPU permit around a call to ``provider``; a no-op for hosted providers."""
    if provider_supports(provider, LOCAL_DEVICE):
        return device_permit_slot("llm-local", priority=priority, timeout_seconds=timeout_seconds)
    return nullcontext()


__all__ = ["llm_admission"]
