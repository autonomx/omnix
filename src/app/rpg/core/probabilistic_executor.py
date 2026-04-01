"""Probabilistic Action Executor — Uncertainty and failure model.

This module implements CRITICAL PATCH 5 from the RPG design specification:
"NO FAILURE / UNCERTAINTY MODEL"

The Problem: Everything succeeds deterministically and executes perfectly.
Without failure, there's no tension, no surprise, and no realism.

The Solution: A ProbabilisticActionExecutor that applies success rates
to actions and generates failure events when actions don't succeed.

Architecture:
    action → check_success_rate() → succeed/fail → execute/return_failure

Usage:
    executor = ProbabilisticActionExecutor()
    result = executor.execute_with_uncertainty(action)
    # result = {"success": True, "events": [...]} or {"success": False, "events": [...]}

Key Features:
    - Configurable base success rates per action type
    - Skill-based modifiers (NPC stats affect success)
    - Exhaustion penalty from resource system
    - Failure events with descriptive messages
    - Critical success and critical failure rolls
"""

from __future__ import annotations

import random
from typing import Any, Dict, Optional

# Default success rates per action type
DEFAULT_SUCCESS_RATES = {
    "attack": 0.80,
    "heal": 0.90,
    "defend": 0.95,
    "move": 0.98,
    "speak": 0.99,
    "observe": 0.85,
    "wander": 0.99,
    "flee": 0.70,
    "steal": 0.60,
    "persuade": 0.50,
}

# Critical thresholds
DEFAULT_CRITICAL_SUCCESS_RATE = 0.1   # 10% chance of critical success
DEFAULT_CRITICAL_FAILURE_RATE = 0.05  # 5% chance of critical failure


class ProbabilisticActionExecutor:
    """Executes actions with probabilistic success/failure.
    
    Every action has a chance to fail. The executor rolls against
    a success rate and generates appropriate failure events when
    actions don't succeed.
    
    Configuration via executor or per-action override.
    
    Attributes:
        base_rates: Dict of action_type → base success rate.
        critical_success_rate: Chance of critical success.
        critical_failure_rate: Chance of critical failure.
        enable_critical: Enable critical hit/miss mechanics.
    """
    
    def __init__(
        self,
        base_rates: Optional[Dict[str, float]] = None,
        critical_success_rate: float = DEFAULT_CRITICAL_SUCCESS_RATE,
        critical_failure_rate: float = DEFAULT_CRITICAL_FAILURE_RATE,
        enable_critical: bool = True,
    ):
        """Initialize ProbabilisticActionExecutor.
        
        Args:
            base_rates: Action type → success rate mapping.
            critical_success_rate: Probability of critical success.
            critical_failure_rate: Probability of critical failure.
            enable_critical: Enable critical mechanics.
        """
        self.base_rates = base_rates or dict(DEFAULT_SUCCESS_RATES)
        self.critical_success_rate = critical_success_rate
        self.critical_failure_rate = critical_failure_rate
        self.enable_critical = enable_critical
        
    def execute_with_uncertainty(
        self,
        action: Dict[str, Any],
        execute_fn=None,
    ) -> Dict[str, Any]:
        """Execute an action with probabilistic success check.
        
        Args:
            action: The action dict to execute.
            execute_fn: Optional function to call on success.
                If None, returns mock success event.
                If provided, called as execute_fn(action).
                
        Returns:
            Dict with success status and events.
        """
        action_type = action.get("action", "unknown")
        
        # Calculate success probability
        probability = self._calculate_success_probability(action)
        
        # Roll for success
        roll = random.random()
        
        if roll > probability:
            # Action failed
            outcome = self._determine_outcome(action, roll, probability)
            return self._create_failure_result(action, outcome)
            
        # Action succeeded
        outcome = self._determine_outcome(action, roll, probability)
        
        if execute_fn:
            result = execute_fn(action)
            events = result.get("events", [])
        else:
            events = [self._create_success_event(action)]
            
        # Apply outcome modifiers
        if outcome == "critical_success":
            events = self._enhance_critical_success(events, action)
            
        return {
            "success": True,
            "outcome": outcome,
            "events": events,
        }
        
    def _calculate_success_probability(
        self, action: Dict[str, Any]
    ) -> float:
        """Calculate final success probability for an action.
        
        Considers:
        - Base rate for action type
        - Per-action success_rate override
        - Actor skill modifier
        - Exhaustion penalty
        
        Args:
            action: Action dict to calculate for.
            
        Returns:
            Final probability (0.0-1.0).
        """
        action_type = action.get("action", "unknown")
        
        # Per-action override
        if "success_rate" in action:
            base = action["success_rate"]
        else:
            base = self.base_rates.get(action_type, 0.75)
            
        # Skill modifier
        skill_mod = action.get("skill_modifier", 0)
        
        # Exhaustion penalty
        exhaustion = action.get("exhaustion_penalty", 1.0)
        
        # Calculate final
        probability = (base + skill_mod) * exhaustion
        return round(max(0.05, min(0.99, probability)), 3)  # Clamp 5%-99%
        
    def _determine_outcome(
        self, action: Dict[str, Any], roll: float, probability: float
    ) -> str:
        """Determine if outcome is normal, critical success, or critical failure.
        
        Args:
            action: Action dict.
            roll: Random value that was rolled.
            probability: Calculated success probability.
            
        Returns:
            Outcome: "critical_success", "normal_success", "normal_fail",
                     or "critical_failure".
        """
        if not self.enable_critical:
            return "normal_success" if roll <= probability else "normal_fail"
            
        # Critical success: roll is very low (lucky)
        if roll <= self.critical_success_rate and roll <= probability:
            return "critical_success"
            
        # Critical failure: roll is very high (unlucky) AND action failed
        if roll > probability and roll >= (1 - self.critical_failure_rate):
            return "critical_failure"
            
        return "normal_success" if roll <= probability else "normal_fail"
        
    def _create_success_event(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Create a success event.
        
        Args:
            action: Action that succeeded.
            
        Returns:
            Success event dict.
        """
        action_type = action.get("action", "unknown")
        actor = action.get("npc_id", "unknown")
        target = action.get("parameters", {}).get("target", "unknown")
        
        return {
            "type": f"{action_type}_success",
            "source": actor,
            "target": target,
            "action": action,
        }
        
    def _create_failure_result(
        self, action: Dict[str, Any], outcome: str
    ) -> Dict[str, Any]:
        """Create a failure result.
        
        Args:
            action: Action that failed.
            outcome: Failure outcome type.
            
        Returns:
            Failure result dict.
        """
        action_type = action.get("action", "unknown")
        actor = action.get("npc_id", "unknown")
        
        failure_message = self._get_failure_message(action_type, outcome)
        
        event = {
            "type": "action_failure",
            "source": actor,
            "original_action": action_type,
            "outcome": outcome,
            "message": failure_message,
        }
        
        return {
            "success": False,
            "outcome": outcome,
            "events": [event],
        }
        
    def _get_failure_message(self, action_type: str, outcome: str) -> str:
        """Get failure description message.
        
        Args:
            action_type: The action that failed.
            outcome: Outcome type.
            
        Returns:
            Failure message string.
        """
        messages = {
            "attack": {
                "normal_fail": "misses their attack",
                "critical_failure": "trips while attacking and falls flat",
            },
            "heal": {
                "normal_fail": "fails to heal the wound properly",
                "critical_failure": "makes the injury worse while trying to heal",
            },
            "defend": {
                "normal_fail": "fumbles their defense",
                "critical_failure": "leaves themselves wide open defending",
            },
            "move": {
                "normal_fail": "stumbles while moving",
                "critical_failure": "trips and falls while running",
            },
            "speak": {
                "normal_fail": "stumbles over their words",
                "critical_failure": "says something completely embarrassing",
            },
            "flee": {
                "normal_fail": "fails to break away",
                "critical_failure": "slips while fleeing and crashes down",
            },
            "steal": {
                "normal_fail": "fails to grab the item unnoticed",
                "critical_failure": "is caught red-handed trying to steal",
            },
            "persuade": {
                "normal_fail": "makes an unconvincing argument",
                "critical_failure": "accidentally insults everyone present",
            },
        }
        
        return messages.get(action_type, {}).get(
            outcome,
            "fails to accomplish anything"
        )
        
    def _enhance_critical_success(
        self, events: list, action: Dict[str, Any]
    ) -> list:
        """Enhance events for critical success.
        
        Args:
            events: Original events.
            action: Action that critically succeeded.
            
        Returns:
            Enhanced events.
        """
        enhanced = []
        action_type = action.get("action", "unknown")
        
        for event in events:
            event["outcome"] = "critical_success"
            
            # Double damage for attacks
            if action_type == "attack" and "amount" in event:
                event["amount"] = event.get("amount", 0) * 2
                event["critical"] = True
                
            enhanced.append(event)
            
        return enhanced


def create_default_executor() -> ProbabilisticActionExecutor:
    """Create executor with default settings.
    
    Returns:
        Configured ProbabilisticActionExecutor.
    """
    return ProbabilisticActionExecutor()