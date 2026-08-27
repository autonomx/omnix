"""Local workspace authority for supervised agent execution."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
from typing import Any

from .contracts import AgentEvent


class WorkspacePolicyError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


_SAFE_EXECUTABLES = {
    "git",
    "python",
    "python.exe",
    "pytest",
    "ruff",
    "node",
    "npm",
    "npm.cmd",
    "npx",
    "npx.cmd",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
}
_BLOCKED_ARGUMENT_FRAGMENTS = (
    "rm -rf",
    "remove-item -recurse",
    "format-volume",
    "shutdown",
    "restart-computer",
    "stop-computer",
    "reg delete",
    "git push",
    "git clean -fd",
    "git reset --hard",
)


class WorkspaceAuthority:
    def __init__(
        self,
        root: str | Path,
        *,
        allowed_paths: list[str] | None = None,
        forbidden_paths: list[str] | None = None,
        emit: Callable[[AgentEvent], Any] | None = None,
        run_id: str = "workspace",
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.allowed_paths = list(allowed_paths or ["**"])
        self.forbidden_paths = list(forbidden_paths or [])
        self.emit = emit
        self.run_id = run_id

    def resolve_path(self, relative: str | Path = ".") -> Path:
        value = Path(relative)
        if value.is_absolute():
            candidate = value.expanduser().resolve()
        else:
            candidate = (self.root / value).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspacePolicyError("path escapes issued workspace") from exc
        rel = candidate.relative_to(self.root).as_posix() or "."
        if any(candidate.match(pattern) or Path(rel).match(pattern) for pattern in self.forbidden_paths):
            raise WorkspacePolicyError(f"path is forbidden by workspace policy: {rel}")
        if self.allowed_paths and not any(pattern == "**" or Path(rel).match(pattern) for pattern in self.allowed_paths):
            raise WorkspacePolicyError(f"path is outside allowed workspace paths: {rel}")
        return candidate

    def read_text(self, relative: str | Path) -> str:
        path = self.resolve_path(relative)
        return path.read_text(encoding="utf-8")

    def write_text(self, relative: str | Path, content: str) -> None:
        path = self.resolve_path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._event("tool.completed", {"capability": "workspace.write", "path": path.relative_to(self.root).as_posix()})

    def edit_text(self, relative: str | Path, old: str, new: str, *, count: int = 1) -> None:
        if not old:
            raise WorkspacePolicyError("edit old text must be non-empty")
        path = self.resolve_path(relative)
        content = path.read_text(encoding="utf-8")
        occurrences = content.count(old)
        if occurrences < count:
            raise WorkspacePolicyError("edit target not found enough times")
        path.write_text(content.replace(old, new, count), encoding="utf-8")
        self._event("tool.completed", {"capability": "workspace.edit", "path": path.relative_to(self.root).as_posix()})

    def list_entries(self, relative: str | Path = ".") -> list[str]:
        path = self.resolve_path(relative)
        if not path.is_dir():
            raise WorkspacePolicyError("workspace list target is not a directory")
        return sorted(item.relative_to(self.root).as_posix() for item in path.iterdir())

    def search_text(self, query: str, relative: str | Path = ".") -> list[dict[str, object]]:
        if not query:
            return []
        base = self.resolve_path(relative)
        files = [base] if base.is_file() else list(base.rglob("*"))
        matches: list[dict[str, object]] = []
        for path in files:
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for index, line in enumerate(lines, start=1):
                if query in line:
                    matches.append({"path": path.relative_to(self.root).as_posix(), "line": index, "text": line[:500]})
                    if len(matches) >= 500:
                        return matches
        return matches

    def run_command(
        self,
        argv: list[str],
        *,
        timeout_seconds: int = 600,
        environment: dict[str, str] | None = None,
    ) -> CommandResult:
        normalized = self._validate_command(argv)
        env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
        if environment:
            env.update({str(key): str(value) for key, value in environment.items()})
        self._event("tool.started", {"capability": "workspace.command", "argv": normalized})
        completed = subprocess.run(
            normalized,
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, min(timeout_seconds, 3600)),
            check=False,
            shell=False,
        )
        result = CommandResult(tuple(normalized), completed.returncode, completed.stdout[-100_000:], completed.stderr[-100_000:])
        self._event("tool.completed", {"capability": "workspace.command", "argv": normalized, "returncode": result.returncode})
        return result

    def git_status(self) -> str:
        return self.run_command(["git", "status", "--short"]).stdout

    def git_diff(self) -> str:
        result = self.run_command(["git", "diff", "--no-ext-diff", "--"])
        if result.returncode != 0:
            raise WorkspacePolicyError(result.stderr or "git diff failed")
        return result.stdout

    @classmethod
    def create_worktree(cls, repository: str | Path, target: str | Path, *, base_ref: str) -> "WorkspaceAuthority":
        repo = Path(repository).expanduser().resolve()
        target_path = Path(target).expanduser().resolve()
        if target_path.exists():
            raise WorkspacePolicyError("worktree target already exists")
        completed = subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(target_path), base_ref],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            raise WorkspacePolicyError(completed.stderr or "failed to create git worktree")
        return cls(target_path)

    def _validate_command(self, argv: list[str]) -> list[str]:
        if not argv or any(not str(part).strip() for part in argv):
            raise WorkspacePolicyError("command argv must contain non-empty arguments")
        normalized = [str(part) for part in argv]
        executable = Path(normalized[0]).name.casefold()
        if executable not in {item.casefold() for item in _SAFE_EXECUTABLES}:
            raise WorkspacePolicyError(f"executable is not allowed: {normalized[0]}")
        joined = " ".join(normalized).casefold()
        if any(fragment in joined for fragment in _BLOCKED_ARGUMENT_FRAGMENTS):
            raise WorkspacePolicyError("command is blocked by workspace policy")
        if executable == "git" and len(normalized) > 1 and normalized[1].casefold() in {"push", "clean"}:
            raise WorkspacePolicyError("remote/destructive git command is broker-controlled")
        return normalized

    def _event(self, event_type: str, payload: dict[str, object]) -> None:
        if self.emit is not None:
            self.emit(AgentEvent(run_id=self.run_id, event_type=event_type, payload=payload))
