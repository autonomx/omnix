"""Deterministic Clock for RPG System.

PHASE 5.2 — DETERMINISTIC CLOCK (rpg-design.txt Issue #2):
Provides a deterministic, injectable clock to replace time.time()
for reproducibility in tests, replay, and simulation.

Usage:
    clock = DeterministicClock()
    loop = GameLoop(..., event_bus=EventBus(clock=clock))
"""


class DeterministicClock:
    """Deterministic clock that advances on each call.
    
    This clock provides predictable timestamps for deterministic
    game execution. Each call to now() advances time by a fixed
    increment.
    
    Attributes:
        _time: Current simulated time value.
        _increment: Amount to advance time on each call (default 0.001).
    """
    
    def __init__(self, start_time: float = 0.0, increment: float = 0.001):
        """Initialize the deterministic clock.
        
        Args:
            start_time: Initial time value (default 0.0).
            increment: Amount to advance on each now() call (default 0.001).
        """
        self._time = start_time
        self._increment = increment
    
    def now(self) -> float:
        """Get current time and advance the clock.
        
        Each call returns a strictly increasing timestamp,
        ensuring event ordering is deterministic.
        
        Returns:
            Current simulated timestamp.
        """
        self._time += self._increment
        return self._time
    
    def current_time(self) -> float:
        """Get current time without advancing.
        
        Returns:
            Current simulated timestamp.
        """
        return self._time
    
    def set_time(self, value: float) -> None:
        """Set the current time to a specific value.
        
        Useful for time-travel debugging or loading snapshots.
        
        Args:
            value: The time value to set.
        """
        self._time = value
    
    def advance(self, amount: float) -> float:
        """Advance the clock by a specific amount.
        
        Args:
            amount: Amount to advance time.
            
        Returns:
            New time value after advancing.
        """
        self._time += amount
        return self._time
    
    def reset(self) -> None:
        """Reset the clock to initial state."""
        self._time = 0.0