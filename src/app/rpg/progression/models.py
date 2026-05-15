from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class ProgressionAction:
    action_id: str
    command: str
    semantic: str
    target_type: str = ""
    target_id: str = ""
    priority: int = 50
    mechanic: str = ""
    required_mechanic: str = ""
    completes_mechanic: str = ""
    completion_flags: List[str] = field(default_factory=list)
    changed_parts: List[str] = field(default_factory=list)
    effects: Dict[str, Any] = field(default_factory=dict)
    display: Dict[str, Any] = field(default_factory=dict)
    action_terms: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProgressionNode:
    node_id: str
    title: str
    requires: List[Dict[str, Any]] = field(default_factory=list)
    action_patterns: List[Dict[str, Any]] = field(default_factory=list)
    suggested_actions: List[ProgressionAction] = field(default_factory=list)
    effects: List[Dict[str, Any]] = field(default_factory=list)
    repeatable: bool = False
    priority: int = 50
    objective_type: str = ""
    required_mechanics: List[str] = field(default_factory=list)


@dataclass
class ScenarioProgressionGraph:
    graph_id: str
    scenario_seed: str
    nodes: List[ProgressionNode] = field(default_factory=list)
    title: str = ""
    priority: int = 50
    starts_after_graph_ids: List[str] = field(default_factory=list)
    starts_after_quest_ids: List[str] = field(default_factory=list)