"""Pure code generation helpers for the autoplay runtime fragments."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


def rewrite_autoplay_fragment_line(line: str) -> str:
    """Redirect fragment Path aliases and write hooks to the private CLI type."""

    path_import = re.fullmatch(
        r"(?P<indent>\s*)from pathlib import Path(?:\s+as\s+(?P<alias>[A-Za-z_]\w*))?(?:\s+#.*)?",
        line,
    )
    if path_import:
        name = path_import.group("alias") or "Path"
        return f"{path_import.group('indent')}{name} = _AUTOPLAY_PATH_CLASS"

    write_hook = re.fullmatch(
        r"(?P<indent>\s*)(?P<owner>[A-Za-z_]\w*)\.write_text\s*=\s*(?P<hook>[A-Za-z_]\w*)(?:\s+#.*)?",
        line,
    )
    if write_hook:
        return (
            f"{write_hook.group('indent')}_install_autoplay_path_write_hook("
            f"{write_hook.group('owner')}, {write_hook.group('hook')})"
        )
    return line


def combine_autoplay_campaign_fragments(fragments: Iterable[Path]) -> str:
    """Combine ordered fragments, hoisting and deduplicating future imports."""

    future_imports: list[str] = []
    seen_futures: set[str] = set()
    body_parts: list[str] = []
    for fragment in fragments:
        body_lines: list[str] = []
        for line in fragment.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("from __future__ import "):
                if stripped not in seen_futures:
                    seen_futures.add(stripped)
                    future_imports.append(stripped)
                continue
            body_lines.append(rewrite_autoplay_fragment_line(line))
        body_parts.append("\n".join(body_lines))
    prefix = "\n".join(future_imports)
    body = "\n".join(body_parts)
    return f"{prefix}\n\n{body}" if prefix else body


def autoplay_campaign_fragments(parts_dir: Path) -> list[Path]:
    fragments = sorted(
        path
        for path in parts_dir.glob("*.pyfrag")
        if not path.name.startswith("chunk_")
    )
    if not fragments:
        raise RuntimeError(f"No autoplay campaign source fragments found in {parts_dir}")
    return fragments
