"""The small set of process responsibilities granted by deployment topology."""

from dataclasses import dataclass
from enum import Enum

from .config import RuntimeConfig


class RuntimeCapability(str, Enum):
    SERVE_API = "serve_api"
    OWN_BACKGROUND_RUNTIME = "own_background_runtime"
    RUN_LOCAL_TTS = "run_local_tts"
    USE_REMOTE_TTS = "use_remote_tts"
    RUN_CHAT_DISPATCH = "run_chat_dispatch"
    RUN_RECOVERY = "run_recovery"
    RUN_SCHEDULERS = "run_schedulers"


@dataclass(frozen=True, slots=True)
class RuntimeCapabilities:
    granted: frozenset[RuntimeCapability]

    def __post_init__(self):
        object.__setattr__(self, 'granted', frozenset(RuntimeCapability(value) for value in self.granted))

    @classmethod
    def from_config(cls, config: RuntimeConfig):
        # Request-driven Chat execution has a durable per-process owner on both
        # roles. Singleton recovery/schedulers belong only to the worker.
        granted = {RuntimeCapability.SERVE_API, RuntimeCapability.RUN_CHAT_DISPATCH}
        if config.owns_background_runtime:
            granted.update({RuntimeCapability.OWN_BACKGROUND_RUNTIME, RuntimeCapability.RUN_RECOVERY, RuntimeCapability.RUN_SCHEDULERS})
        if config.allow_local_tts:
            granted.add(RuntimeCapability.RUN_LOCAL_TTS)
        if config.use_remote_tts:
            granted.add(RuntimeCapability.USE_REMOTE_TTS)
        return cls(frozenset(granted))

    def allows(self, capability: RuntimeCapability) -> bool:
        return capability in self.granted

    def require(self, *capabilities: RuntimeCapability) -> None:
        missing = set(capabilities) - self.granted
        if missing:
            raise RuntimeError(f"Process lacks runtime capabilities: {sorted(value.value for value in missing)}")
