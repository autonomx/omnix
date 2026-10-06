"""A throwaway worktree and a fresh database for the module recipe tests (PA-4.2, PA-4.3)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

ROOT = Path(__file__).resolve().parents[3]


def run_checked(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, f"{' '.join(command)} failed:\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}"
    return result


@pytest.fixture
def worktree():
    """HEAD plus the working tree's changes and new files, in a throwaway worktree."""
    path = Path(tempfile.mkdtemp(prefix="omnix-recipe-")) / "tree"
    run_checked(["git", "worktree", "add", "-q", "--detach", str(path), "HEAD"], ROOT)
    try:
        patch = subprocess.run(["git", "diff", "HEAD", "--binary"], cwd=ROOT, capture_output=True, check=True).stdout
        if patch:
            subprocess.run(["git", "apply", "--whitespace=nowarn"], cwd=path, input=patch, check=True)
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", "src/app", "src/tests", "scripts", "resources"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.split()
        for name in untracked:
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        run_checked(["git", "add", "-A", "--", "src", "scripts", "resources"], path)
        yield path
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=ROOT, capture_output=True)
        shutil.rmtree(path.parent, ignore_errors=True)


@pytest.fixture
def fresh_database():
    base = os.environ.get("OMNIX_TEST_DATABASE_URL")
    if not base:
        pytest.skip("OMNIX_TEST_DATABASE_URL is required")
    import psycopg

    admin_url = os.environ.get("OMNIX_TEST_ADMIN_DATABASE_URL") or os.environ.get("OMNIX_MIGRATION_DATABASE_URL") or base
    name = f"omnix_recipe_{uuid.uuid4().hex[:8]}"
    maintenance = urlunsplit(urlsplit(admin_url)._replace(path="/postgres"))
    try:
        with psycopg.connect(maintenance, autocommit=True) as admin:
            if not admin.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
                pytest.skip("the recipe test needs a superuser test database (fresh database and probe role)")
            admin.execute(f'CREATE DATABASE "{name}"')
    except psycopg.errors.InsufficientPrivilege:
        pytest.skip("the test role cannot create databases")
    try:
        yield urlunsplit(urlsplit(admin_url)._replace(path=f"/{name}"))
    finally:
        with psycopg.connect(maintenance, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
