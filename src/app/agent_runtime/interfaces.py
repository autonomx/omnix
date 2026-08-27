"""Runtime interfaces shared by workflows and iterative agents."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from .contracts import AgentArtifact, AgentEvent, AgentRunCommand, AgentRunSnapshot, AgentRunSpec


class AgentRuntime(ABC):
    @abstractmethod
    def start(self, spec: AgentRunSpec) -> AgentRunSnapshot: ...

    @abstractmethod
    def command(self, command: AgentRunCommand) -> AgentRunSnapshot: ...

    def steer(self, run_id: str, message: str) -> AgentRunSnapshot:
        return self.command(AgentRunCommand(run_id=run_id, command_type="steer", payload={"message": message}))

    def pause(self, run_id: str) -> AgentRunSnapshot:
        return self.command(AgentRunCommand(run_id=run_id, command_type="pause"))

    def resume(self, run_id: str) -> AgentRunSnapshot:
        return self.command(AgentRunCommand(run_id=run_id, command_type="resume"))

    def cancel(self, run_id: str) -> AgentRunSnapshot:
        return self.command(AgentRunCommand(run_id=run_id, command_type="cancel"))

    @abstractmethod
    def get_status(self, run_id: str) -> AgentRunSnapshot | None: ...

    @abstractmethod
    def stream_events(self, run_id: str, *, after_sequence: int = 0) -> Iterable[AgentEvent]: ...

    @abstractmethod
    def get_artifacts(self, run_id: str) -> list[AgentArtifact]: ...


class WorkflowRuntime(ABC):
    @abstractmethod
    def start(self, workflow_id: str, input_payload: dict[str, object]) -> str: ...

    @abstractmethod
    def pause(self, run_id: str) -> None: ...

    @abstractmethod
    def resume(self, run_id: str) -> None: ...

    @abstractmethod
    def cancel(self, run_id: str) -> None: ...

    @abstractmethod
    def get_status(self, run_id: str) -> dict[str, object] | None: ...
