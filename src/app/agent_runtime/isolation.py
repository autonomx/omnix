"""OS/process isolation backends for agent workers.

A Git worktree is change isolation only. Strong/unattended execution requires a
configured container image and a restricted Docker network supplied by the
operator; otherwise the launch fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .contracts import AgentRunSpec


class AgentIsolationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IsolationLimits:
    memory: str = "4g"
    cpus: str = "2"
    pids: int = 256
    tmpfs_size: str = "256m"


def _popen(argv: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )


class LocalSupervisedIsolation:
    name = "supervised_worktree"
    strong = False

    def launch(self, spec: AgentRunSpec, *, argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[str]:
        return _popen(argv, cwd=cwd, env=env)


class DockerStrongIsolation:
    name = "docker_strong"
    strong = True

    def __init__(
        self,
        *,
        image: str | None = None,
        network: str | None = None,
        limits: IsolationLimits | None = None,
    ) -> None:
        self.docker = shutil.which("docker")
        self.image = image or os.environ.get("OMNIX_AGENT_DOCKER_IMAGE")
        self.network = network or os.environ.get("OMNIX_AGENT_DOCKER_NETWORK")
        self.limits = limits or IsolationLimits(
            memory=os.environ.get("OMNIX_AGENT_DOCKER_MEMORY", "4g"),
            cpus=os.environ.get("OMNIX_AGENT_DOCKER_CPUS", "2"),
            pids=int(os.environ.get("OMNIX_AGENT_DOCKER_PIDS", "256")),
            tmpfs_size=os.environ.get("OMNIX_AGENT_DOCKER_TMPFS", "256m"),
        )

    def validate(self) -> None:
        if not self.docker:
            raise AgentIsolationError("docker_strong isolation requires Docker")
        if not self.image:
            raise AgentIsolationError("docker_strong isolation requires OMNIX_AGENT_DOCKER_IMAGE")
        if not self.network:
            raise AgentIsolationError(
                "docker_strong isolation requires OMNIX_AGENT_DOCKER_NETWORK; "
                "configure a restricted network that can reach only the Omnix broker/model gateway"
            )

    def build_command(self, spec: AgentRunSpec, *, argv: list[str], cwd: Path, env: dict[str, str]) -> list[str]:
        self.validate()
        extension_dir = Path(__file__).resolve().parent
        rewritten = self._rewrite_pi_argv(argv, extension_dir)
        command = [
            str(self.docker),
            "run",
            "--rm",
            "-i",
            "--name",
            f"omnix-agent-{spec.run_id[:24]}",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--network",
            str(self.network),
            "--memory",
            self.limits.memory,
            "--cpus",
            self.limits.cpus,
            "--pids-limit",
            str(self.limits.pids),
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,size={self.limits.tmpfs_size}",
            "--mount",
            f"type=bind,source={cwd},target=/workspace",
            "--mount",
            f"type=bind,source={extension_dir},target=/omnix-agent-runtime,readonly",
            "--workdir",
            "/workspace",
        ]
        container_env = self._container_env(spec, env)
        for key, value in sorted(container_env.items()):
            command.extend(["--env", f"{key}={value}"])
        command.extend([str(self.image), *rewritten])
        return command

    def launch(self, spec: AgentRunSpec, *, argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[str]:
        command = self.build_command(spec, argv=argv, cwd=cwd, env=env)
        host_env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
        return _popen(command, cwd=cwd, env=host_env)

    @staticmethod
    def _rewrite_pi_argv(argv: list[str], extension_dir: Path) -> list[str]:
        result = ["pi"]
        skip_first = True
        for item in argv:
            if skip_first:
                skip_first = False
                continue
            path = Path(item)
            if path.is_absolute():
                try:
                    relative = path.resolve().relative_to(extension_dir)
                except ValueError:
                    result.append(item)
                else:
                    result.append(f"/omnix-agent-runtime/{relative.as_posix()}")
            else:
                result.append(item)
        return result

    @staticmethod
    def _container_env(
        spec: AgentRunSpec,
        env: dict[str, str],
    ) -> dict[str, str]:
        explicit = {
            str(key or "").strip()
            for key in spec.execution.allowed_environment_keys
            if str(key or "").strip()
        }
        allowed = {
            key: value
            for key, value in env.items()
            if key.startswith("OMNIX_AGENT_") or key in explicit
        }
        allowed["OMNIX_AGENT_WORKSPACE"] = "/workspace"
        if os.environ.get("OMNIX_AGENT_CONTAINER_MODEL_GATEWAY_URL"):
            allowed["OMNIX_AGENT_MODEL_GATEWAY_URL"] = os.environ["OMNIX_AGENT_CONTAINER_MODEL_GATEWAY_URL"]
        if os.environ.get("OMNIX_AGENT_CONTAINER_BROKER_URL"):
            allowed["OMNIX_AGENT_BROKER_URL"] = os.environ["OMNIX_AGENT_CONTAINER_BROKER_URL"]
        return allowed


def isolation_for_spec(spec: AgentRunSpec):
    policy = spec.workspace.isolation_policy if spec.workspace else "supervised_worktree"
    if policy in {"docker_strong", "unattended"}:
        return DockerStrongIsolation()
    if policy == "supervised_worktree":
        return LocalSupervisedIsolation()
    raise AgentIsolationError(f"unknown agent isolation policy: {policy}")


def launch_agent_process(
    spec: AgentRunSpec,
    *,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
) -> subprocess.Popen[str]:
    isolation = isolation_for_spec(spec)
    if spec.workspace and spec.workspace.isolation_policy == "unattended" and not isolation.strong:
        raise AgentIsolationError("unattended agent execution requires strong isolation")
    return isolation.launch(spec, argv=argv, cwd=cwd, env=env)
