"""Rolling-upgrade acceptance test (roadmap WP-6.7).

Runs version N (two gateway replicas and two job workers) against a
disposable PostgreSQL database, keeps a steady request and job load on it, and
then rolls every process, one at a time, to a simulated N+1: the same code
with an extra expand migration, a new software revision and a new feature
flag. It asserts:

* no failed requests, other than requests a draining replica refused before
  doing any work (503 ``draining`` or connection refused), which are retried;
* every submitted job completes exactly once (one completed attempt);
* draining replicas report ``/ready`` 503 ``draining``, and replacements report
  the N+1 revision.

Usage::

    OMNIX_DATABASE_URL=postgresql://.../omnix_test \
        python scripts/rolling_upgrade_test.py --output artifacts/rolling-upgrade.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
VERSION_N = "rolling-N"
VERSION_N1 = "rolling-N+1"
PROBE_MIGRATION = "9990_rolling_upgrade_probe.sql"
PROBE_SQL = (
    "-- omnix-migration: phase=expand transactional=true\n"
    "CREATE TABLE IF NOT EXISTS omnix_rolling_upgrade_probe (\n"
    "    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,\n"
    "    note TEXT\n"
    ");\n"
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _require_disposable(url: str, allow: bool) -> None:
    name = (urlsplit(url).path or "").lstrip("/")
    if not allow and "test" not in name:
        raise SystemExit(
            f"refusing to run against database {name!r}: use a disposable *test* database "
            "or pass --allow-database"
        )


class Process:
    def __init__(self, name: str, command: list[str], env: dict[str, str], log_dir: Path) -> None:
        self.name = name
        self.command = command
        self.env = env
        self.log_path = log_dir / f"{name}-{int(time.time() * 1000)}.log"
        self.handle: subprocess.Popen[str] | None = None

    def start(self) -> None:
        log = self.log_path.open("w", encoding="utf-8")
        self.handle = subprocess.Popen(
            self.command,
            cwd=ROOT,
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )

    def request_stop(self) -> None:
        # The managed-stdin control line takes the same drain path as SIGTERM.
        assert self.handle is not None and self.handle.stdin is not None
        try:
            self.handle.stdin.write("stop\n")
            self.handle.stdin.flush()
            self.handle.stdin.close()
        except (OSError, ValueError):
            pass

    def wait(self, timeout: float) -> int:
        assert self.handle is not None
        try:
            return self.handle.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.handle.kill()
            self.handle.wait(10)
            raise RuntimeError(f"{self.name} did not exit within {timeout:.0f}s; see {self.log_path}")

    def kill(self) -> None:
        if self.handle is not None and self.handle.poll() is None:
            self.handle.kill()
            self.handle.wait(10)


class Topology:
    def __init__(self, database_url: str, log_dir: Path, drain_seconds: int) -> None:
        self.database_url = database_url
        self.log_dir = log_dir
        self.drain_seconds = drain_seconds
        self.service_token = secrets.token_urlsafe(32)
        self.gateways: dict[str, tuple[Process, int]] = {}
        self.workers: dict[str, Process] = {}
        self.lock = threading.Lock()

    def _env(self, role: str, version: str, *, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "PYTHONPATH": str(SRC) + os.pathsep + env.get("PYTHONPATH", ""),
                "OMNIX_DATABASE_URL": self.database_url,
                "OMNIX_ENV": "test",
                "OMNIX_GATEWAY_BACKGROUND_ROLE": role,
                "OMNIX_LOCAL_JOB_WORKER": "0",
                "OMNIX_SERVICE_TOKEN": self.service_token,
                "OMNIX_SOFTWARE_REVISION": version,
                "OMNIX_DRAIN_SECONDS": str(self.drain_seconds),
                # Like a production ingress probe interval: stay visibly
                # not-ready for a moment even when idle.
                "OMNIX_DRAIN_MIN_SECONDS": "2",
                "OMNIX_JOB_WORKER_SHUTDOWN_GRACE_SECONDS": str(self.drain_seconds),
                "OMNIX_JOB_WORKER_POOLS": "cpu=2",
            }
        )
        env.pop("OMNIX_AUTH_MODE", None)
        if role == "job-worker":
            env.pop("OMNIX_GATEWAY_OWNS_BACKGROUND_RUNTIME", None)
        env.update(extra or {})
        return env

    def start_gateway(self, name: str, role: str, version: str, port: int, extra: dict[str, str] | None = None) -> None:
        command = [
            sys.executable, str(ROOT / "scripts/run_omnix_gateway.py"),
            "--app", "app.composition.gateway.runtime_app:app", "--host", "127.0.0.1",
            "--port", str(port), "--api-replicas", "0", "--managed-stdin",
        ]
        process = Process(name, command, self._env(role, version, extra=extra), self.log_dir)
        process.start()
        with self.lock:
            self.gateways[name] = (process, port)

    def start_worker(self, name: str, version: str, extra: dict[str, str] | None = None) -> None:
        command = [
            sys.executable, "-m", "app.composition.worker", "--managed-stdin",
            "--metrics-port", str(_free_port()),
        ]
        process = Process(name, command, self._env("job-worker", version, extra=extra), self.log_dir)
        process.start()
        self.workers[name] = process

    def ports(self) -> list[int]:
        with self.lock:
            return [port for _process, port in self.gateways.values()]

    def wait_ready(self, port: int, *, revision: str, timeout: float = 180) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: Any = None
        while time.monotonic() < deadline:
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/ready", timeout=5)
                last = response.json()
                if response.status_code == 200 and last.get("build_revision") == revision:
                    return last
            except (httpx.HTTPError, ValueError) as exc:
                last = repr(exc)
            time.sleep(0.5)
        raise RuntimeError(f"gateway on port {port} not ready as {revision}: {last}")

    def stop_all(self) -> None:
        for process, _port in list(self.gateways.values()):
            process.request_stop()
        for process in self.workers.values():
            process.request_stop()
        for process, _port in list(self.gateways.values()):
            try:
                process.wait(self.drain_seconds + 30)
            except RuntimeError:
                pass
        for process in self.workers.values():
            try:
                process.wait(self.drain_seconds + 30)
            except RuntimeError:
                pass


class Load:
    """Steady request and job load that retries only refused-before-work requests."""

    def __init__(self, topology: Topology, *, threads: int, job_duration_ms: int) -> None:
        self.topology = topology
        self.threads = threads
        self.job_duration_ms = job_duration_ms
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.job_ids: list[str] = []
        self.requests = 0
        self.retries = 0
        self.failures: list[str] = []
        self.cursor = 0

    def _next_port(self) -> int | None:
        ports = self.topology.ports()
        if not ports:
            return None
        with self.lock:
            self.cursor += 1
            return ports[self.cursor % len(ports)]

    def _call(self, method: str, path: str, body: dict[str, Any] | None) -> httpx.Response | None:
        for _attempt in range(40):
            port = self._next_port()
            if port is None:
                time.sleep(0.2)
                continue
            try:
                response = httpx.request(
                    method,
                    f"http://127.0.0.1:{port}{path}",
                    json=body,
                    headers={"X-Omnix-Client": "rolling-upgrade-test"},
                    timeout=30,
                )
            except httpx.ConnectError:
                # Refused before the request reached the application.
                with self.lock:
                    self.retries += 1
                time.sleep(0.05)
                continue
            if response.status_code == 503 and _is_draining(response):
                with self.lock:
                    self.retries += 1
                continue
            return response
        return None

    def _worker(self, index: int) -> None:
        sequence = 0
        while not self.stop.is_set():
            sequence += 1
            key = f"rolling-{index}-{sequence}-{secrets.token_hex(4)}"
            body = {
                "module": "platform",
                "type": "platform.probe",
                "resource_class": "cpu",
                "input_payload": {"duration_ms": self.job_duration_ms, "label": key[:64]},
                "compat": {"idempotency_key": key},
            }
            for method, path, payload in (("POST", "/api/jobs", body), ("GET", "/api/jobs?limit=5", None)):
                try:
                    response = self._call(method, path, payload)
                except httpx.HTTPError as exc:
                    # Includes a connection lost mid-request: a real failure.
                    with self.lock:
                        self.requests += 1
                        self.failures.append(f"{method} {path}: {type(exc).__name__}: {exc}")
                    continue
                with self.lock:
                    self.requests += 1
                    if response is None:
                        self.failures.append(f"{method} {path}: no replica accepted the request")
                    elif response.status_code >= 400:
                        self.failures.append(f"{method} {path}: HTTP {response.status_code} {response.text[:200]}")
                    elif method == "POST":
                        self.job_ids.append(str(response.json()["id"]))
            time.sleep(0.05)

    def run(self) -> list[threading.Thread]:
        threads = [
            threading.Thread(target=self._worker, args=(index,), name=f"load-{index}", daemon=True)
            for index in range(self.threads)
        ]
        for thread in threads:
            thread.start()
        return threads


def _is_draining(response: httpx.Response) -> bool:
    try:
        return response.json().get("detail") == "draining"
    except ValueError:
        return False


def _apply_n1_migration(database_url: str, workdir: Path) -> list[str]:
    sys.path.insert(0, str(SRC))
    os.environ["OMNIX_DATABASE_URL"] = database_url
    from app.persistence.migrations import apply_migrations, migration_root

    root = workdir / "migrations-n1"
    shutil.copytree(migration_root(), root)
    (root / PROBE_MIGRATION).write_text(PROBE_SQL, encoding="utf-8")
    status = apply_migrations(root=root)
    return list(status.get("applied_now") or [])


def _job_outcomes(database_url: str, job_ids: list[str]) -> dict[str, Any]:
    import psycopg

    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT job.id, job.status,
                   count(*) FILTER (WHERE attempt.status = 'completed') AS completed_attempts,
                   count(attempt.job_id) AS attempts
              FROM omnix_jobs AS job
              LEFT JOIN omnix_job_attempts AS attempt ON attempt.job_id = job.id
             WHERE job.id = ANY(%s)
             GROUP BY job.id, job.status
            """,
            (job_ids,),
        ).fetchall()
    by_id = {str(row[0]): (str(row[1]), int(row[2]), int(row[3])) for row in rows}
    return {
        "missing": [job_id for job_id in job_ids if job_id not in by_id],
        "not_completed": sorted(job_id for job_id, row in by_id.items() if row[0] != "completed"),
        "duplicate_completions": sorted(job_id for job_id, row in by_id.items() if row[1] > 1),
        "retried_after_release": sum(1 for row in by_id.values() if row[2] > 1),
    }


def _wait_jobs_terminal(database_url: str, job_ids: list[str], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    outcome = _job_outcomes(database_url, job_ids)
    while outcome["not_completed"] and time.monotonic() < deadline:
        time.sleep(1)
        outcome = _job_outcomes(database_url, job_ids)
    return outcome


def _roll_gateway(topology: Topology, name: str, role: str, report: dict[str, Any]) -> None:
    process, port = topology.gateways[name]
    process.request_stop()
    observed = None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/ready", timeout=2)
        except httpx.HTTPError:
            break
        if response.status_code == 503 and response.json().get("reason") == "draining":
            observed = response.json()
            break
        time.sleep(0.05)
    with topology.lock:
        topology.gateways.pop(name)
    exit_code = process.wait(topology.drain_seconds + 30)
    new_port = _free_port()
    topology.start_gateway(f"{name}-n1", role, VERSION_N1, new_port, extra={"OMNIX_ROLLING_PROBE_FLAG": "1"})
    ready = topology.wait_ready(new_port, revision=VERSION_N1)
    report["gateways"].append(
        {
            "replaced": name,
            "drain_ready_observed": observed,
            "exit_code": exit_code,
            "replacement_revision": ready.get("build_revision"),
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--job-duration-ms", type=int, default=300)
    parser.add_argument("--warmup-seconds", type=float, default=5)
    parser.add_argument("--drain-seconds", type=int, default=10)
    parser.add_argument("--allow-database", action="store_true")
    args = parser.parse_args()

    database_url = os.environ.get("OMNIX_DATABASE_URL", "")
    if not database_url:
        raise SystemExit("OMNIX_DATABASE_URL is required")
    _require_disposable(database_url, args.allow_database)

    workdir = Path(tempfile.mkdtemp(prefix="omnix-rolling-"))
    log_dir = workdir / "logs"
    log_dir.mkdir()
    topology = Topology(database_url, log_dir, args.drain_seconds)
    report: dict[str, Any] = {"measurement": "rolling-upgrade", "gateways": [], "workers": []}
    load = Load(topology, threads=args.threads, job_duration_ms=args.job_duration_ms)
    started = time.monotonic()
    try:
        topology.start_gateway("gateway-worker", "worker", VERSION_N, _free_port())
        topology.start_gateway("gateway-api", "api", VERSION_N, _free_port())
        topology.start_worker("job-worker-a", VERSION_N)
        topology.start_worker("job-worker-b", VERSION_N)
        for port in topology.ports():
            topology.wait_ready(port, revision=VERSION_N)

        threads = load.run()
        time.sleep(args.warmup_seconds)

        report["n1_migrations_applied"] = _apply_n1_migration(database_url, workdir)
        _roll_gateway(topology, "gateway-api", "api", report)
        time.sleep(1)
        _roll_gateway(topology, "gateway-worker", "worker", report)
        for name in ("job-worker-a", "job-worker-b"):
            worker = topology.workers.pop(name)
            worker.request_stop()
            code = worker.wait(args.drain_seconds + 30)
            topology.start_worker(f"{name}-n1", VERSION_N1, extra={"OMNIX_ROLLING_PROBE_FLAG": "1"})
            report["workers"].append({"replaced": name, "exit_code": code})
            time.sleep(1)

        time.sleep(args.warmup_seconds)
        load.stop.set()
        for thread in threads:
            thread.join(60)
        outcome = _wait_jobs_terminal(database_url, list(load.job_ids), timeout=120)
    finally:
        load.stop.set()
        topology.stop_all()

    report.update(
        {
            "duration_seconds": round(time.monotonic() - started, 1),
            "requests": load.requests,
            "retried_refusals": load.retries,
            "failed_requests": load.failures[:50],
            "failed_request_count": len(load.failures),
            "jobs_submitted": len(load.job_ids),
            "jobs": outcome,
            "logs": str(log_dir),
        }
    )
    problems = []
    if load.failures:
        problems.append(f"{len(load.failures)} failed requests")
    if not load.job_ids:
        problems.append("no jobs were submitted")
    if outcome["missing"] or outcome["not_completed"]:
        problems.append("jobs did not all complete")
    if outcome["duplicate_completions"]:
        problems.append("duplicate job execution")
    if any(item["drain_ready_observed"] is None for item in report["gateways"]):
        problems.append("a draining replica never reported /ready 503 draining")
    if any(item["replacement_revision"] != VERSION_N1 for item in report["gateways"]):
        problems.append("a replacement did not report the N+1 revision")
    report["result"] = "failed" if problems else "passed"
    report["problems"] = problems
    encoded = json.dumps(report, indent=2, sort_keys=True)
    print(encoded)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
