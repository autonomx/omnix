"""Generalized Omnix agent/workflow runtime foundations."""

from .capabilities import (
    Capability,
    CapabilityEffect,
    CapabilityExecutionZone,
    CapabilityRegistry,
    CapabilityRisk,
    default_capability_registry,
)

__all__ = [
    "Capability",
    "CapabilityEffect",
    "CapabilityExecutionZone",
    "CapabilityRegistry",
    "CapabilityRisk",
    "default_capability_registry",
]
