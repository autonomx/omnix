"""Disposable evidence must not use an operator DB or mutate the source tree."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("omnix_runtime_metrics_tests_target", SCRIPTS / "architecture_runtime_metrics.py")
runtime = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(runtime)
URL = "postgresql://tester:disposable-test-only@127.0.0.1:55871/omnix_test"


@pytest.mark.parametrize("url", [
    "", "postgresql://tester@provider.example:5432/omnix_test",
    "postgresql://tester@127.0.0.1:5432/omnix_production",
    "postgresql://tester@localhost/omnix_test", "postgresql://localhost:5432/omnix_test",
    URL + "?host=provider.example", URL + "?dbname=omnix_production",
    URL + "?service=operator", URL + "#ignored",
])
def test_database_audience_must_be_explicit_loopback_and_disposable(url):
    with pytest.raises(ValueError):
        runtime.disposable_url(url)


def test_explicit_disposable_database_audience_is_accepted():
    assert runtime.disposable_url(URL) == URL


def test_guard_enforces_real_filesystem_network_and_subprocess_audits(tmp_path):
    owned = tmp_path / "owned"
    owned.mkdir()
    source = tmp_path / "source.txt"
    source.write_text("operator input", encoding="utf-8")
    code = f"""
import sys, socket, subprocess
from pathlib import Path
sys.path.insert(0, {str(SCRIPTS)!r})
from architecture_runtime_metrics import install_probe_guard
install_probe_guard(Path({str(tmp_path)!r}), Path({str(owned)!r}), {URL!r})
Path({str(owned / 'allowed.txt')!r}).write_text('allowed')
assert Path({str(source)!r}).read_text() == 'operator input'
for operation in [
    lambda: Path({str(source)!r}).write_text('changed'),
    lambda: Path({str(source)!r}).unlink(),
    lambda: Path({str(owned / 'allowed.txt')!r}).rename({str(source)!r}),
    lambda: socket.socket().connect(('198.51.100.1', 443)),
    lambda: socket.socket().connect(('127.0.0.1', 12345)),
    lambda: subprocess.run([sys.executable, '-c', 'pass']),
]:
    try:
        operation()
    except PermissionError:
        pass
    else:
        raise AssertionError('probe escaped its disposable boundaries')
print('guard verified')
"""
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard verified"
    assert source.read_text(encoding="utf-8") == "operator input"
    assert (owned / "allowed.txt").read_text() == "allowed"


def test_snapshot_copies_tracked_inputs_without_untracked_operator_state(tmp_path):
    root, target = tmp_path / "source", tmp_path / "snapshot"
    root.mkdir()
    files = {"src/app/a.py": "value = 1", "resources/logo.png": "binary fixture", "vendor/unsafe.py": "value = 2"}
    for name, contents in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "--", *files], check=True, capture_output=True)
    (root / "operator-secret.txt").write_text("untracked input", encoding="utf-8")
    runtime.disposable_snapshot(root, target)
    assert (target / "src/app/a.py").read_text(encoding="utf-8") == "value = 1"
    assert (target / "resources/logo.png").read_bytes() == (root / "resources/logo.png").read_bytes()
    assert not (target / "vendor").exists()
    assert not (target / "operator-secret.txt").exists()


def test_snapshot_cannot_be_certified_under_a_different_source_digest(tmp_path):
    snapshot = tmp_path / "repository"
    file = snapshot / "src/app/a.py"
    file.parent.mkdir(parents=True)
    file.write_text("value = 2", encoding="utf-8")
    with pytest.raises(ValueError, match="source changed"):
        runtime.verify_snapshot({"src/app/a.py": "value = 1"}, snapshot)
    runtime.verify_snapshot({"src/app/a.py": "value = 2"}, snapshot)


def test_initial_outbox_probe_requires_registry_measurement_once_consumers_exist():
    config = runtime.load_layers(SCRIPTS.parent / "resources/architecture/layers.toml")
    assert runtime.outbox_initial_coverage({}, config)[0] == 0
    with pytest.raises(ValueError, match="runtime registry"):
        runtime.outbox_initial_coverage({"src/app/worker.py": "registry.register_consumer(spec)"}, config)


def test_database_coverage_uses_enabled_policies_and_tenant_tables():
    class Connection:
        rows = iter([
            [("omnix_jobs", True), ("omnix_workspaces", False)],
            [("outbox_events",), ("job_attempts",)],
            [({"outbox_events": 0, "disabled_policy": 7},)],
        ])

        def execute(self, query):
            self.result = next(self.rows)
            return self

        def fetchall(self):
            return self.result

    values, evidence = runtime.database_metrics(Connection())
    assert values == {"rls_coverage_pct": 50, "retention_policies_executed_pct": 50}
    assert evidence["retention_policies_executed"] == ["outbox_events"]


@pytest.mark.parametrize("source,success", [
    ("def test_ok():\n    assert True\n", True),
    ("answer = 42\n", False),
    ("raise KeyboardInterrupt\n", False),
])
def test_collection_probe_cannot_certify_empty_or_interrupted_collection(tmp_path, source, success):
    root = tmp_path / "repository"
    root.mkdir()
    file = root / "test_subject.py"
    file.write_text(source, encoding="utf-8")
    manifest, output = tmp_path / "manifest.json", tmp_path / "collection.json"
    manifest.write_text(json.dumps({"root": str(root), "test_paths": [str(file)]}), encoding="utf-8")
    result = subprocess.run([
        sys.executable, "-I", str(SCRIPTS / "architecture_runtime_metrics.py"),
        "--child", "collection", "--manifest", str(manifest), "--output", str(output),
    ], cwd=root, env=dict(os.environ, OMNIX_TEST_DATABASE_URL=URL), capture_output=True, text=True, timeout=20)
    report = json.loads(output.read_text(encoding="utf-8"))
    if success:
        assert result.returncode == 0
        assert report["metrics"] == {"collection_errors": 0}
        assert report["evidence"]["collected_tests"] == 1
        assert report["evidence"]["collection_finished"] is True
    else:
        assert result.returncode != 0
        assert "metrics" not in report
        assert report["error"] == "probe_failed"
