"""A typed view of a campaign document, section by section (RQ-1.1).

``CampaignStateView(document)`` reads each section on first use and keeps the reading; it never changes the
document. Untyped code keeps reading the document's paths as before; typed code (the reducer, TurnOutcome,
new resolvers) reads the view.
"""
from __future__ import annotations

from collections.abc import Mapping
from functools import cached_property
from typing import Any

from .sections import (
    SECTIONS,
    CombatSection,
    EconomySection,
    InteractionsSection,
    InventorySection,
    LocationSection,
    MetaSection,
    NarrativeSection,
    NpcsSection,
    PartySection,
    PlayerSection,
    QuestsSection,
    Section,
    SurvivalSection,
    TimeSection,
    WorldSection,
)


class CampaignStateView:
    """The sections of one campaign document, typed."""

    def __init__(self, document: Mapping[str, Any]) -> None:
        self.document = document

    def section(self, name: str) -> Section:
        return getattr(self, name)

    @cached_property
    def player(self) -> PlayerSection:
        return PlayerSection.from_document(self.document)

    @cached_property
    def inventory(self) -> InventorySection:
        return InventorySection.from_document(self.document)

    @cached_property
    def location(self) -> LocationSection:
        return LocationSection.from_document(self.document)

    @cached_property
    def time(self) -> TimeSection:
        return TimeSection.from_document(self.document)

    @cached_property
    def party(self) -> PartySection:
        return PartySection.from_document(self.document)

    @cached_property
    def combat(self) -> CombatSection:
        return CombatSection.from_document(self.document)

    @cached_property
    def quests(self) -> QuestsSection:
        return QuestsSection.from_document(self.document)

    @cached_property
    def survival(self) -> SurvivalSection:
        return SurvivalSection.from_document(self.document)

    @cached_property
    def npcs(self) -> NpcsSection:
        return NpcsSection.from_document(self.document)

    @cached_property
    def interactions(self) -> InteractionsSection:
        return InteractionsSection.from_document(self.document)

    @cached_property
    def world(self) -> WorldSection:
        return WorldSection.from_document(self.document)

    @cached_property
    def economy(self) -> EconomySection:
        return EconomySection.from_document(self.document)

    @cached_property
    def narrative(self) -> NarrativeSection:
        return NarrativeSection.from_document(self.document)

    @cached_property
    def meta(self) -> MetaSection:
        return MetaSection.from_document(self.document)

    def validate(self) -> dict[str, Section]:
        """Every section read (``pydantic.ValidationError`` if one cannot be)."""
        return {name: self.section(name) for name in SECTIONS}
