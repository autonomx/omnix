"""
JavaScript variable conflict detection – migrated from test_js_variables.py.

Static analysis tests that parse JS files and detect duplicate global
variable declarations across files.
"""

from __future__ import annotations

import re
import pytest
from pathlib import Path

from utils.helpers import (
    get_js_files,
    extract_global_vars,
    COMMON_LOCAL_VARS,
    STATIC_DIR,
)


class TestJSVariableConflicts:
    """Detect JS global variable declaration conflicts."""

    def test_no_duplicate_global_vars(self):
        """No global variables should be declared in multiple JS files."""
        js_files = get_js_files()
        assert len(js_files) > 0, "No JS files found in static directory"

        all_global_vars: dict[str, tuple[Path, int]] = {}
        conflicts: list[dict] = []

        for js_file in js_files:
            global_vars = extract_global_vars(js_file)
            for var_name, line_num in global_vars.items():
                if var_name in COMMON_LOCAL_VARS:
                    continue
                if var_name in all_global_vars:
                    prev_file, prev_line = all_global_vars[var_name]
                    conflicts.append(
                        {
                            "variable": var_name,
                            "file1": str(js_file.relative_to(STATIC_DIR.parent)),
                            "line1": line_num,
                            "file2": str(prev_file.relative_to(STATIC_DIR.parent)),
                            "line2": prev_line,
                        }
                    )
                else:
                    all_global_vars[var_name] = (js_file, line_num)

        if conflicts:
            msg = "\n\nJavaScript global variable conflicts detected:\n"
            for c in conflicts:
                msg += f"  - '{c['variable']}' declared in:\n"
                msg += f"      {c['file1']}:{c['line1']}\n"
                msg += f"      {c['file2']}:{c['line2']}\n"
            pytest.fail(msg)

    def test_no_global_var_shadowing_in_same_file(self):
        """Variables should not be declared twice in the same file."""
        js_files = get_js_files()
        errors: list[str] = []

        for js_file in js_files:
            global_vars = extract_global_vars(js_file)
            seen: dict[str, int] = {}
            for var_name, line_num in global_vars.items():
                if var_name in seen:
                    errors.append(
                        f"{js_file.relative_to(STATIC_DIR.parent)}:{line_num}: "
                        f"'{var_name}' already declared at line {seen[var_name]}"
                    )
                seen[var_name] = line_num

        if errors:
            pytest.fail("\n".join(errors))

    def test_no_undeclared_global_access(self):
        """Warn about assignments to well-known browser globals."""
        js_files = get_js_files()

        common_globals = {
            "window", "document", "navigator", "console", "setTimeout",
            "setInterval", "fetch", "WebSocket", "AudioContext", "AudioWorklet",
            "performance", "location", "history", "localStorage", "sessionStorage",
            "FormData", "Blob", "File", "URL", "URLSearchParams",
        }

        issues: list[str] = []
        for js_file in js_files:
            content = js_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.split("\n"), 1):
                if line.strip().startswith("//"):
                    continue
                for global_name in common_globals:
                    if re.search(rf"\b{global_name}\s*=\s*", line):
                        issues.append(
                            f"{js_file.relative_to(STATIC_DIR.parent)}:{i}: "
                            f"Assigning to global '{global_name}'"
                        )

        if issues:
            print("\n⚠️  Potential issues (may be false positives):")
            for issue in issues[:10]:
                print(f"  {issue}")

    def test_specific_known_conflicts(self):
        """Check for historically problematic variable names."""
        js_files = get_js_files()
        known_conflicts = ["sessionId", "audioContext", "ws", "isConnected", "isSpeaking"]

        file_vars: dict[str, dict[str, int]] = {}
        for js_file in js_files:
            file_vars[str(js_file.relative_to(STATIC_DIR.parent))] = extract_global_vars(js_file)

        conflicts_found: list[str] = []
        for var_name in known_conflicts:
            files_with_var = [f for f, vs in file_vars.items() if var_name in vs]
            if len(files_with_var) > 1:
                conflicts_found.append(
                    f"'{var_name}' declared in multiple files: {files_with_var}"
                )

        if conflicts_found:
            pytest.fail("\n".join(conflicts_found))
