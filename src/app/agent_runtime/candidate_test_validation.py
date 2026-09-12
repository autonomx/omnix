"""Candidate-derived execution evidence for run-owned regression tests.

The static TaskRevision validation plan cannot know about regression tests that the
coding agent creates during implementation or repair.  Independent review must not
start merely because some other ``final-state-tests`` command passed on the same
workspace state: every executable test file in the authoritative run-owned subject
needs fresh execution evidence for that exact candidate.

This module is deliberately deterministic.  It classifies test paths from the
RunChangeSet subject, matches exact-state ValidationResult rows, and has a narrow
fallback for test runners (notably Playwright) that older command classification may
not yet persist as ValidationResult rows.  The fallback is accepted only when the
successful test command occurs after the last potentially workspace-mutating tool
completion in the durable event stream.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import re
from typing import Iterable

from .contracts import AgentEvent, ValidationResult, ValidationSpec


_EXECUTABLE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".php",
    ".cs",
    ".c",
    ".cpp",
    ".cc",
    ".sh",
    ".ps1",
}
_NON_EXECUTABLE_SEGMENTS = {
    "__snapshots__",
    "snapshots",
    "fixtures",
    "fixture",
    "testdata",
    "test-data",
    "__mocks__",
    "mocks",
}
_NON_EXECUTABLE_BASENAMES = {
    "conftest.py",
    "playwright.config.js",
    "playwright.config.ts",
    "vitest.config.js",
    "vitest.config.ts",
    "jest.config.js",
    "jest.config.ts",
}
_JS_TEST_RE = re.compile(r"(?:^|\.)(?:test|spec)\.(?:[cm]?js|jsx|ts|tsx)$", re.I)
_PY_TEST_RE = re.compile(r"^(?:test_.+|.+_test)\.py$", re.I)
_GO_TEST_RE = re.compile(r".+_test\.go$", re.I)
_JAVA_TEST_RE = re.compile(r".+(?:Test|Tests)\.java$")
_GENERIC_TEST_RE = re.compile(r".+(?:_test|_tests)\.(?:rb|php|cs|c|cc|cpp|rs|sh|ps1)$", re.I)
_TEST_FILE_TOKEN_RE = re.compile(
    r"[^\s\"']+(?:\.test|\.spec)\.(?:[cm]?js|jsx|ts|tsx)|"
    r"[^\s\"']*(?:^|[/\\])test_[^\s\"']+\.py|"
    r"[^\s\"']+_test\.(?:py|go|rb|php|cs|c|cc|cpp|rs|sh|ps1)|"
    r"[^\s\"']+(?:Test|Tests)\.java",
    re.I,
)
_TEST_COMMAND_RE = re.compile(
    r"\bpytest\b|\bvitest\b|\bjest\b|\bplaywright\s+test\b|"
    r"\bnpx\s+(?:--yes\s+)?playwright\s+test\b|"
    r"\b(?:npm|npm\.cmd|pnpm|yarn)\b[^\r\n]*\btest\b|"
    r"\bgo\s+test\b|\bcargo\s+test\b|\bdotnet\s+test\b|"
    r"\b(?:mvn|mvnw|gradle|gradlew)\b[^\r\n]*\btest\b",
    re.I,
)
_TARGETING_SELECTOR_RE = re.compile(
    r"(?:^|\s)(?:-k|-t|--grep|--grep-invert|--filter|--testNamePattern|--test-name-pattern)(?:=|\s)",
    re.I,
)
_READ_ONLY_SHELL_RE = re.compile(
    r"^\s*(?:git\s+(?:status|diff|show|log|rev-parse)|pwd\b|ls\b|dir\b|cat\b|type\b|"
    r"rg\b|grep\b|findstr\b)",
    re.I,
)
_NON_MUTATING_VALIDATION_RE = re.compile(
    r"\b(?:pytest|vitest|jest|playwright\s+test|typecheck|tsc|ruff|eslint|lint)\b|"
    r"\b(?:npm|npm\.cmd|pnpm|yarn)\b[^\r\n]*\b(?:test|build|typecheck|lint)\b|"
    r"\b(?:go|cargo|dotnet)\s+test\b",
    re.I,
)
_READ_ONLY_TOOLS = {
    "read",
    "ls",
    "grep",
    "search",
    "omnix_change_set",
    "omnix_capability",
    "git_status",
}
_SHELL_TOOLS = {"bash", "powershell"}
_MUTATING_TOOLS = {"edit", "write"}


def _normalize_path(value: str) -> str:
    normalized = str(value or "").strip().replace("\\", "/").lstrip("./")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def is_executable_test_path(path: str) -> bool:
    """Return whether a run-owned path denotes a directly executable test file."""

    normalized = _normalize_path(path)
    if not normalized or normalized.endswith("/"):
        return False
    parts = [part.casefold() for part in normalized.split("/") if part]
    if any(part in _NON_EXECUTABLE_SEGMENTS for part in parts[:-1]):
        return False
    basename = parts[-1] if parts else ""
    if basename in _NON_EXECUTABLE_BASENAMES:
        return False
    dot = basename.rfind(".")
    extension = basename[dot:] if dot >= 0 else ""
    if extension not in _EXECUTABLE_EXTENSIONS:
        return False
    original_basename = normalized.rsplit("/", 1)[-1]
    return bool(
        _JS_TEST_RE.search(original_basename)
        or _PY_TEST_RE.match(original_basename)
        or _GO_TEST_RE.match(original_basename)
        or _JAVA_TEST_RE.match(original_basename)
        or _GENERIC_TEST_RE.match(original_basename)
    )


def executable_candidate_test_paths(paths: Iterable[str]) -> list[str]:
    """Return normalized, unique run-owned executable test paths."""

    return sorted(
        {
            normalized
            for path in paths
            if (normalized := _normalize_path(path)) and is_executable_test_path(normalized)
        }
    )


def candidate_test_validation_specs(paths: Iterable[str]) -> list[ValidationSpec]:
    """Build deterministic same-candidate validation requests for missing test files."""

    specs: list[ValidationSpec] = []
    for path in executable_candidate_test_paths(paths):
        digest = hashlib.sha256(path.casefold().encode("utf-8")).hexdigest()[:16]
        specs.append(
            ValidationSpec(
                id=f"candidate-test-execution-{digest}",
                kind="test",
                description=(
                    "Execute this run-owned regression test against the exact final candidate before independent "
                    f"review: {path}"
                ),
                covers=[],
                required=True,
                command_hint=f"Run this exact test file with its repository test runner: {path}",
            )
        )
    return specs


def _test_command(command: str) -> bool:
    return bool(_TEST_COMMAND_RE.search(str(command or "")))


def _path_aliases(path: str, *, basename_unique: bool) -> list[str]:
    normalized = _normalize_path(path).casefold()
    aliases = [normalized]
    parts = normalized.split("/")
    for marker in ("tests", "test", "e2e", "specs", "spec"):
        if marker in parts:
            aliases.append("/".join(parts[parts.index(marker) :]))
    if basename_unique:
        aliases.append(parts[-1])
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _command_coverage(command: str, required_paths: list[str]) -> set[str]:
    """Return candidate test paths proved executed by one successful test command."""

    if not _test_command(command):
        return set()
    folded = str(command or "").replace("\\", "/").casefold()
    basename_counts = Counter(path.rsplit("/", 1)[-1].casefold() for path in required_paths)
    explicit: set[str] = set()
    for path in required_paths:
        basename = path.rsplit("/", 1)[-1].casefold()
        aliases = _path_aliases(path, basename_unique=basename_counts[basename] == 1)
        if any(alias in folded for alias in aliases):
            explicit.add(path)
    if explicit:
        return explicit

    # A command naming some other concrete test file or using a test-name/filter
    # selector is targeted and cannot prove that every run-owned test executed.
    if _TEST_FILE_TOKEN_RE.search(str(command or "")) or _TARGETING_SELECTOR_RE.search(str(command or "")):
        return set()

    # Directory-scoped commands such as ``pytest tests/agent_runtime`` cover only
    # candidate tests below the named test directory.  Bare runner commands cover
    # the whole candidate test set.
    directory_covered: set[str] = set()
    for path in required_paths:
        parts = path.casefold().split("/")
        for index, part in enumerate(parts[:-1]):
            if part not in {"tests", "test", "e2e", "specs", "spec"}:
                continue
            prefix = "/".join(parts[: index + 1])
            tail = "/".join(parts[index: index + 1])
            if prefix in folded or re.search(rf"(?:^|\s)[\"']?{re.escape(tail)}(?:[/\s\"']|$)", folded):
                directory_covered.add(path)
                break
    if directory_covered:
        return directory_covered
    return set(required_paths)


def _event_command(started: AgentEvent | None, completed: AgentEvent) -> str:
    args = started.payload.get("args") if started and isinstance(started.payload.get("args"), dict) else {}
    return str(args.get("command") or completed.payload.get("command") or "").strip()


def _event_tool(started: AgentEvent | None, completed: AgentEvent) -> str:
    return str(completed.payload.get("tool") or (started.payload.get("tool") if started else "") or "").strip()


def _exit_code_from_payload(payload: object) -> int | None:
    if isinstance(payload, dict):
        for key in ("exit_code", "exitCode"):
            value = payload.get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
        for key in ("details", "result"):
            nested = payload.get(key)
            code = _exit_code_from_payload(nested)
            if code is not None:
                return code
    return None


def _completed_test_succeeded(event: AgentEvent) -> bool:
    if event.payload.get("is_error"):
        return False
    return _exit_code_from_payload(event.payload.get("result")) == 0


def _potential_workspace_mutation(tool: str, command: str) -> bool:
    folded_tool = str(tool or "").strip().casefold()
    if folded_tool in _MUTATING_TOOLS:
        return True
    if folded_tool in _READ_ONLY_TOOLS:
        return False
    if folded_tool in _SHELL_TOOLS:
        if _test_command(command) or _READ_ONLY_SHELL_RE.search(command) or _NON_MUTATING_VALIDATION_RE.search(command):
            return False
        return True
    # Fail closed for unknown tool families: raw-event fallback evidence is only
    # trusted when no later operation could plausibly have changed the candidate.
    return True


def _raw_final_state_test_coverage(events: Iterable[AgentEvent], required_paths: list[str]) -> set[str]:
    ordered = list(events)
    started_by_call_id = {
        str(event.payload.get("tool_call_id") or ""): event
        for event in ordered
        if event.event_type == "tool.started" and str(event.payload.get("tool_call_id") or "")
    }
    completed_rows: list[tuple[int, AgentEvent, AgentEvent | None, str, str]] = []
    for index, event in enumerate(ordered):
        if event.event_type != "tool.completed":
            continue
        call_id = str(event.payload.get("tool_call_id") or "")
        started = started_by_call_id.get(call_id)
        command = _event_command(started, event)
        tool = _event_tool(started, event)
        sequence = int(event.sequence) if event.sequence is not None else index
        completed_rows.append((sequence, event, started, tool, command))

    last_mutation_sequence = max(
        (
            sequence
            for sequence, _event, _started, tool, command in completed_rows
            if _potential_workspace_mutation(tool, command)
        ),
        default=-1,
    )
    covered: set[str] = set()
    for sequence, event, _started, _tool, command in completed_rows:
        if sequence < last_mutation_sequence or not _test_command(command) or not _completed_test_succeeded(event):
            continue
        covered.update(_command_coverage(command, required_paths))
    return covered


def missing_candidate_test_execution(
    subject_paths: Iterable[str],
    validations: Iterable[ValidationResult],
    *,
    workspace_state_id: str,
    events: Iterable[AgentEvent] = (),
) -> list[str]:
    """Return run-owned executable tests lacking fresh final-candidate execution evidence."""

    required = executable_candidate_test_paths(subject_paths)
    if not required:
        return []

    covered: set[str] = set()
    for validation in validations:
        if (
            validation.workspace_state_id != workspace_state_id
            or validation.kind != "test"
            or not validation.success
            or validation.outcome != "passed"
        ):
            continue
        covered.update(_command_coverage(validation.command, required))

    # Older command classification did not recognize every E2E runner (notably
    # direct Playwright invocations).  Preserve exact-state safety by accepting
    # raw successful commands only when they occur after the last potentially
    # mutating durable tool completion.
    covered.update(_raw_final_state_test_coverage(events, required))
    return [path for path in required if path not in covered]
