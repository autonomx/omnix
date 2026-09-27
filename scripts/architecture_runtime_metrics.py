"""Produce architecture runtime evidence in a guarded disposable environment.

The scorecard itself remains standard-library-only. This opt-in probe requires
the repository's existing Python dependencies, an explicit disposable test DB,
and imports/tests only tracked source. It never starts ASGI lifespan workers.
"""

from __future__ import annotations

import argparse
import ast
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from architecture_analysis import AnalysisError, SourceAnalysis, included_path, is_test, load_layers, qualified_name, source_digest, tracked_sources

ROOT = Path(__file__).resolve().parents[1]


def disposable_snapshot(root: Path, destination: Path) -> None:
    """Copy tracked working-tree inputs; never include operator/untracked data."""
    names = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout.decode("utf-8").split("\0")
    for name in sorted(set(names)):
        if not name or not included_path(name):
            continue
        source = root / name
        if not source.exists():
            continue
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root.resolve()):
            raise AnalysisError(f"tracked snapshot input is not a regular repository file: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def verify_snapshot(sources: dict[str, str], snapshot: Path) -> None:
    copied = {name: (snapshot / name).read_bytes().decode("utf-8-sig") for name in sources}
    if source_digest(copied) != source_digest(sources):
        raise ValueError("source changed while creating the disposable snapshot; no baseline can be certified")


def disposable_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"postgresql", "postgres"}
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.path not in {"/omnix_test", "/omnix_refactor_baseline"}
            or parsed.port is None or not parsed.username or parsed.query or parsed.fragment):
        raise ValueError("architecture probes require an explicit loopback disposable test database")
    return value


def measurement_profile() -> dict:
    # Called after counting boot imports so reporting does not alter the count.
    import importlib.metadata
    import platform

    names = ("pytest", "fastapi", "uvicorn", "httpx", "pydantic", "requests",
             "python-multipart", "pillow", "playwright", "numpy", "psutil",
             "psycopg", "psycopg-pool", "rich", "websockets")
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {"python": platform.python_version(), "platform": platform.system(), "dependencies": versions}


def install_probe_guard(root: Path, temporary: Path, database_url: str) -> None:
    """Refuse provider connections and writes outside the probe's temporary dir."""
    parsed = urlsplit(database_url)
    allowed_port = parsed.port or 5432
    writable = temporary.resolve()

    def permitted_path(value) -> bool:
        if isinstance(value, int):
            return value in {0, 1, 2}
        try:
            return Path(os.fsdecode(value)).resolve().is_relative_to(writable)
        except (TypeError, ValueError, OSError):
            return False

    def guard(event, arguments):
        if event == "socket.connect":
            address = arguments[1]
            if (not isinstance(address, tuple) or len(address) < 2
                    or address[0] not in {"127.0.0.1", "localhost", "::1"}
                    or address[1] != allowed_port):
                raise PermissionError("architecture probe refuses provider network access")
        if event == "open":
            path, mode, flags = arguments
            writing = isinstance(mode, str) and any(character in mode for character in "wax+")
            writing |= isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and not permitted_path(path):
                raise PermissionError("architecture probe refuses writes outside its temporary directory")
        if event in {"os.remove", "os.rmdir", "os.mkdir"} and not permitted_path(arguments[0]):
            raise PermissionError("architecture probe refuses filesystem mutation")
        if event in {"os.rename", "os.link", "os.symlink"} and not all(permitted_path(path) for path in arguments[:2]):
            raise PermissionError("architecture probe refuses filesystem mutation")
        if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            raise PermissionError("architecture probe refuses child processes")

    sys.addaudithook(guard)


def database_metrics(connection) -> tuple[dict, dict]:
    tenant_tables = connection.execute(
        "WITH RECURSIVE tenant_relations(oid) AS ("
        "SELECT relation.oid FROM pg_class AS relation "
        "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
        "WHERE namespace.nspname = 'public' AND relation.relkind IN ('r', 'p') "
        "AND relation.relname LIKE 'omnix_%' "
        "AND (relation.relname = 'omnix_workspaces' OR EXISTS (SELECT 1 FROM pg_attribute AS attribute "
        "WHERE attribute.attrelid = relation.oid AND attribute.attname = 'workspace_id' "
        "AND attribute.attnum > 0 AND NOT attribute.attisdropped)) "
        "UNION SELECT constraint_row.conrelid FROM pg_constraint AS constraint_row "
        "JOIN tenant_relations AS tenant ON tenant.oid = constraint_row.confrelid "
        "WHERE constraint_row.contype = 'f') "
        "SELECT relation.relname, relation.relrowsecurity "
        "FROM pg_class AS relation JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
        "JOIN tenant_relations AS tenant ON tenant.oid = relation.oid "
        "WHERE namespace.nspname = 'public' AND relation.relkind IN ('r', 'p') "
        "AND relation.relname LIKE 'omnix_%' ORDER BY relation.relname"
    ).fetchall()
    policies = [row[0] for row in connection.execute(
        "SELECT record_type FROM omnix_retention_policies WHERE enabled ORDER BY record_type"
    ).fetchall()]
    runs = connection.execute(
        "SELECT deleted_counts FROM omnix_lifecycle_cleanup_runs "
        "WHERE status = 'completed' AND completed_at >= clock_timestamp() - INTERVAL '48 hours'"
    ).fetchall()
    # The current lifecycle repository uses shortened report keys for these
    # two policy identities. Keep the mapping explicit until WP-5.2 unifies it.
    aliases = {"consumer_inbox": "outbox_consumer_inbox", "dead_letters": "outbox_dead_letters"}
    recorded = set().union(*(row[0].keys() for row in runs)) if runs else set()
    executed = {aliases.get(name, name) for name in recorded}
    return {
        "rls_coverage_pct": round(100 * sum(bool(row[1]) for row in tenant_tables) / len(tenant_tables), 6) if tenant_tables else 0,
        "retention_policies_executed_pct": round(100 * len(set(policies) & executed) / len(policies), 6) if policies else 0,
    }, {"tenant_tables": [{"table": row[0], "rls_enabled": bool(row[1])} for row in tenant_tables],
        "enabled_retention_policies": policies, "retention_policies_executed": sorted(set(policies) & executed)}


def outbox_initial_coverage(sources: dict[str, str], config: dict) -> tuple[int, dict]:
    """Verify the current absence of consumers instead of assuming it forever.

WP-5.3 introduces OutboxConsumerSpec and its runtime registry. The first such
registration must replace this initial probe with a registry-backed coverage
measurement; it cannot keep reporting the pre-relay zero without evidence.
"""
    analysis = SourceAnalysis(sources, config)
    candidates = []
    for path, tree in analysis.trees.items():
        if not path.startswith("src/app/") or is_test(path) or path.startswith("src/app/persistence/"):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and qualified_name(node.func).split(".")[-1] in {"OutboxConsumerSpec", "claim_batch", "register_consumer"}:
                candidates.append(path)
    if candidates:
        raise ValueError("outbox consumers require a runtime registry coverage probe")
    return 0, {"consumer_registration_callers": [], "reason": "no relay consumer registration or outbox claimant in production source"}


def child_probe(mode: str, manifest_path: Path, output: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root, temporary = Path(manifest["root"]), manifest_path.parent
    url = disposable_url(os.environ.get("OMNIX_TEST_DATABASE_URL", ""))
    # libpq connection environment must not override the validated audience.
    for name in tuple(os.environ):
        if name.startswith("PG"):
            os.environ.pop(name)
    os.environ["OMNIX_DATABASE_URL"] = url
    os.environ["OMNIX_PERSISTENCE_MODE"] = "postgresql"
    os.environ["OMNIX_GATEWAY_ROLE"] = "api"
    os.environ["OMNIX_STATE_STORE"] = str(temporary / "state")
    os.environ["OMNIX_SECRET_STORE"] = "env"
    os.environ["TEMP"] = str(temporary)
    os.environ["TMP"] = str(temporary)
    sys.dont_write_bytecode = True
    install_probe_guard(root, temporary, url)
    sys.path.insert(0, str(root / "src"))
    result = {}
    # Module/provider diagnostics are captured inside this process. The report
    # contains only selected measurements and identifiers, never raw failures.
    captured = io.StringIO()
    diagnostics = {}
    try:
        with redirect_stdout(captured), redirect_stderr(captured):
            if mode == "boot":
                before = set(sys.modules)
                from app.production import create_production_app
                from app.runtime_config import RuntimeConfig, GatewayRole
                from app.persistence.database import close_default_database
                try:
                    application = create_production_app(RuntimeConfig(gateway_role=GatewayRole.API))
                    assert application.state.runtime_services is not None
                    imported = sorted(set(sys.modules) - before)
                    result = {"metrics": {"boot_imported_modules": len(imported)}, "evidence": {"boot_module_names": imported, "lifespan_started": False}}
                    result["evidence"]["measurement_profile"] = measurement_profile()
                finally:
                    close_default_database()
            elif mode == "database":
                import psycopg
                with psycopg.connect(url, options="-c default_transaction_read_only=on") as connection:
                    assert connection.execute("SELECT current_database()").fetchone()[0] in {"omnix_test", "omnix_refactor_baseline"}
                    values, evidence = database_metrics(connection)
                    result = {"metrics": values, "evidence": evidence}
            elif mode == "collection":
                import pytest

                class Collector:
                    failures = []
                    failure_kinds = []
                    internal_error = False
                    finished = False
                    collected_tests = 0

                    def pytest_configure(self, config):
                        self.configuration = {
                            "config_file": str(config.inipath.relative_to(root)) if config.inipath else None,
                            "import_mode": config.getoption("importmode"),
                            "strict_markers": bool(config.getoption("strict_markers")),
                        }

                    def pytest_collectreport(self, report):
                        if report.failed:
                            self.failures.append(report.nodeid)
                            text = str(report.longrepr)
                            kind = "probe_boundary" if "architecture probe refuses" in text else "collection"
                            self.failure_kinds.append({"nodeid": report.nodeid, "kind": kind})

                    def pytest_collection_finish(self, session):
                        self.finished = True
                        self.collected_tests = len(session.items)

                    def pytest_internalerror(self, excrepr, excinfo):
                        self.internal_error = True
                        diagnostics["internal_error_type"] = excinfo.typename
                        diagnostics["internal_frames"] = [
                            {"file": Path(entry.path).name, "line": entry.lineno + 1, "function": entry.name}
                            for entry in excinfo.traceback
                        ]

                collector = Collector()
                configuration = []
                for candidate in (root / "pytest.ini", root / "pyproject.toml", root / "src/tests/pytest.ini"):
                    if candidate.exists():
                        configuration = ["-c", str(candidate)]
                        break
                exit_code = pytest.main([
                    "--collect-only", "--continue-on-collection-errors", "-q", "-p", "no:cacheprovider",
                    "--rootdir", str(root), *configuration, "-o", f"log_file={temporary / 'pytest.log'}", *manifest["test_paths"],
                ], plugins=[collector])
                diagnostics["pytest_exit_code"] = int(exit_code)
                if (collector.internal_error or not collector.finished or int(exit_code) not in {0, 1, 2}
                        or not collector.collected_tests and not collector.failures):
                    raise RuntimeError("pytest collection probe did not finish")
                result = {"metrics": {"collection_errors": len(collector.failures)},
                          "evidence": {"collection_failed_nodes": sorted(collector.failures), "pytest_exit_code": int(exit_code)}}
                result["evidence"]["collection_failure_kinds"] = sorted(collector.failure_kinds, key=lambda failure: (failure["nodeid"], failure["kind"]))
                result["evidence"]["pytest_configuration"] = collector.configuration
                result["evidence"]["collected_tests"] = collector.collected_tests
                result["evidence"]["collection_finished"] = collector.finished
            else:
                raise ValueError("unknown architecture probe")
    except Exception as exc:
        result = {"error": "probe_failed", "exception_type": type(exc).__name__, "mode": mode,
                  "frames": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                             for frame in traceback.extract_tb(exc.__traceback__)], "diagnostics": diagnostics}
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return int("error" in result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "resources/architecture/runtime-metrics.json")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--child", choices=["boot", "database", "collection"], help=argparse.SUPPRESS)
    parser.add_argument("--manifest", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.child:
        return child_probe(args.child, args.manifest, args.output)
    try:
        disposable_url(os.environ.get("OMNIX_TEST_DATABASE_URL", ""))
        root = args.root.resolve()
        sources = tracked_sources(root)
        config = load_layers(root / "resources/architecture/layers.toml")
        outbox, outbox_evidence = outbox_initial_coverage(sources, config)
        values, evidence = {"outbox_consumer_coverage_pct": outbox}, {"outbox": outbox_evidence}
        with tempfile.TemporaryDirectory(prefix="omnix-architecture-probe-") as temporary_name:
            temporary = Path(temporary_name)
            snapshot = temporary / "repository"
            disposable_snapshot(root, snapshot)
            verify_snapshot(sources, snapshot)
            probe_script = snapshot / "scripts/architecture_runtime_metrics.py"
            if not probe_script.is_file():
                raise ValueError("architecture probe tooling must be tracked before measuring the repository")
            test_paths = sorted(str(snapshot / path) for path in sources if path.endswith(".py") and _test_path(path))
            if not test_paths:
                raise ValueError("no tracked tests are available for the collection probe")
            manifest = temporary / "manifest.json"
            manifest.write_text(json.dumps({"root": str(snapshot), "test_paths": test_paths}), encoding="utf-8")
            for mode in ("boot", "database", "collection"):
                output = temporary / f"{mode}.json"
                process = subprocess.run([
                    sys.executable, "-I", str(probe_script), "--child", mode,
                    "--manifest", str(manifest), "--output", str(output),
                ], cwd=snapshot, capture_output=True, timeout=args.timeout)
                if process.returncode or not output.exists():
                    detail = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
                    frames = " > ".join(f"{frame['file']}:{frame['line']}:{frame['function']}" for frame in detail.get("frames", []))
                    internal = detail.get("diagnostics", {})
                    if internal:
                        frames += " " + json.dumps(internal, sort_keys=True)
                    raise ValueError(f"{mode} probe failed ({detail.get('exception_type', 'process_error')}) [{frames}]; no baseline can be certified")
                observed = json.loads(output.read_text(encoding="utf-8"))
                values.update(observed["metrics"])
                evidence[mode] = observed["evidence"]
        report = {"schema_version": 1, "environment": "disposable", "source_digest": source_digest(sources),
                  "measured_at": datetime.now(timezone.utc).isoformat(), "metrics": values, "evidence": evidence}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"metrics": values, "output": str(args.output)}, sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"architecture runtime metrics: {exc}", file=sys.stderr)
        return 1


def _test_path(path: str) -> bool:
    return is_test(path) and Path(path).name.startswith("test_")


if __name__ == "__main__":
    raise SystemExit(main())
