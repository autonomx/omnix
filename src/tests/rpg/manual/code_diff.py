from __future__ import annotations

import difflib
import subprocess
from pathlib import Path
from typing import List

from tests.rpg.manual.constants import (
    CODE_DIFF_EXCLUDE_PARTS,
    CODE_DIFF_PATH,
    DEFAULT_CODE_DIFF_ROOTS,
    REPO_ROOT,
)


def _run_git_command(args: List[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        return completed.stdout or ""
    except Exception as exc:
        return f"[manual][code-diff] git command failed: git {' '.join(args)}\n{type(exc).__name__}: {exc}\n"


def _git_untracked_files_under_roots(roots: List[Path]) -> List[Path]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--others", "--exclude-standard"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception:
        return []

    out: List[Path] = []
    root_resolved = [root.resolve() for root in roots]
    for line in (proc.stdout or "").splitlines():
        rel = line.strip()
        if not rel:
            continue
        path = (REPO_ROOT / rel).resolve()
        if any(path == root or root in path.parents for root in root_resolved):
            out.append(path)
    return sorted(out)


def _format_untracked_file_for_diff(path: Path) -> str:
    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except Exception:
        rel = str(path)

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return (
            f"\n\n# UNTRACKED FILE: {rel}\n"
            f"# Could not read file: {type(exc).__name__}: {exc}\n"
        )

    lines = text.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    return (
        f"\n\n"
        f"diff --git a/{rel} b/{rel}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{rel}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}\n"
    )


def _is_diff_candidate(path: Path, roots: List[str]) -> bool:
    try:
        rel = path.relative_to(REPO_ROOT)
    except ValueError:
        return False

    parts = set(rel.parts)
    if parts & CODE_DIFF_EXCLUDE_PARTS:
        return False

    rel_text = rel.as_posix()
    if not any(rel_text == root or rel_text.startswith(f"{root.rstrip('/')}/") for root in roots):
        return False

    if path.suffix in {".pyc", ".pyo", ".pyd", ".dll", ".exe", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".zip"}:
        return False

    return path.is_file()


def _git_untracked_files(roots: List[str]) -> List[Path]:
    status = _run_git_command(["status", "--porcelain", "--untracked-files=all", "--", *roots])
    paths: List[Path] = []
    for line in status.splitlines():
        if not line.startswith("?? "):
            continue
        raw_path = line[3:].strip()
        if not raw_path:
            continue
        candidate = REPO_ROOT / raw_path
        if _is_diff_candidate(candidate, roots):
            paths.append(candidate)
    return sorted(paths)


def _untracked_file_diff(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).as_posix()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except Exception as exc:
        return f"diff --git a/{rel} b/{rel}\nnew file mode 100644\n[manual][code-diff] failed to read file: {type(exc).__name__}: {exc}\n\n"

    return "".join(
        difflib.unified_diff(
            [],
            lines,
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )


def write_code_diff_snapshot(
    path: Path = CODE_DIFF_PATH,
    *,
    roots: List[str] | None = None,
) -> None:
    if roots is None:
        roots = DEFAULT_CODE_DIFF_ROOTS
    path_roots = [Path(r) for r in roots]
    root_args = [str(r) for r in roots]

    diff = _run_git_command(["diff", "--", *root_args])
    untracked_files = _git_untracked_files_under_roots(path_roots)
    if untracked_files:
        diff += "\n\n# Untracked files included by manual_llm_transcript.py\n"
        for untracked in untracked_files:
            diff += _format_untracked_file_for_diff(untracked)
    path.write_text(diff, encoding="utf-8")