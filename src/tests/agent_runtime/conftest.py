from __future__ import annotations

import os
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def agent_workspace_roots(monkeypatch, tmp_path_factory):
    """Agents may change only allow-listed folders (WP-4.7); tests use pytest's temp folders."""
    if "OMNIX_AGENT_WORKSPACE_ROOTS" not in os.environ:
        roots = [str(REPOSITORY), str(REPOSITORY / "resources" / "agent_workspaces"), str(tmp_path_factory.getbasetemp())]
        monkeypatch.setenv("OMNIX_AGENT_WORKSPACE_ROOTS", os.pathsep.join(roots))
