"""Multi-host topology test and capacity benchmark (roadmap WP-6.8).

Runs inside the ``docker-compose.multihost-test.yml`` network: two API
replicas, one worker/scheduler gateway, two job workers, a fake model
service, PostgreSQL and an S3-compatible store behind Nginx. Each Omnix
container has its own filesystem, so anything that only works through a
shared local disk fails here.

Checks, through Nginx unless stated:

* chat: a session created on one replica answers through the fake model
  and the reply is read back from another replica;
* jobs: ``platform.probe`` jobs complete exactly once across both workers
  (verified in PostgreSQL);
* events: the event stream reports the submitted job;
* assets: an image uploaded to the worker host downloads from an API replica
  (only possible through the shared S3 bucket);
* live call: the TTS WebSocket streams PCM from the remote TTS service.

It then runs a mixed load for ``--duration-seconds`` and records p50, p95
and p99 latency and throughput per operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import httpx

HEADERS = {"X-Omnix-Client": "multihost-topology-test"}
FAKE_REPLY = "Multi-host topology reply."
FAKE_MODEL = "omnix-fake-model"


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 2)


class Recorder:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.samples: dict[str, list[float]] = {}
        self.errors: dict[str, list[str]] = {}

    def timed(self, name: str, operation: Callable[[], Any]) -> Any:
        started = time.perf_counter()
        try:
            result = operation()
        except Exception as exc:
            with self.lock:
                self.errors.setdefault(name, []).append(f"{type(exc).__name__}: {exc}"[:300])
            return None
        elapsed = (time.perf_counter() - started) * 1000
        with self.lock:
            self.samples.setdefault(name, []).append(elapsed)
        return result

    def summary(self, duration: float) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in sorted(set(self.samples) | set(self.errors)):
            values = self.samples.get(name, [])
            result[name] = {
                "count": len(values),
                "errors": len(self.errors.get(name, [])),
                "error_examples": self.errors.get(name, [])[:3],
                "p50_ms": _percentile(values, 0.50),
                "p95_ms": _percentile(values, 0.95),
                "p99_ms": _percentile(values, 0.99),
                "mean_ms": round(statistics.fmean(values), 2) if values else 0.0,
                "throughput_per_second": round(len(values) / duration, 3) if duration else 0.0,
            }
        return result


def _check(response: httpx.Response) -> Any:
    response.raise_for_status()
    return response.json() if response.content else None


def wait_ready(urls: list[str], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    status: dict[str, Any] = {}
    pending = list(urls)
    while pending and time.monotonic() < deadline:
        for url in list(pending):
            try:
                response = httpx.get(f"{url}/ready", timeout=5)
                status[url] = response.json()
                if response.status_code == 200:
                    pending.remove(url)
            except (httpx.HTTPError, ValueError) as exc:
                status[url] = repr(exc)
        time.sleep(1)
    if pending:
        raise RuntimeError(f"not ready: {pending}: {json.dumps({u: status.get(u) for u in pending})[:1500]}")
    return status


def create_bucket() -> None:
    from app.persistence.s3_blob_store import S3Settings, SigV4Signer

    endpoint = os.environ["OMNIX_S3_ENDPOINT"]
    settings = S3Settings(
        endpoint=endpoint,
        bucket=os.environ["OMNIX_S3_BUCKET"],
        access_key_id=os.environ["OMNIX_S3_ACCESS_KEY_ID"],
        secret_access_key=os.environ["OMNIX_S3_SECRET_ACCESS_KEY"],
    )
    path = f"/{settings.bucket}"
    deadline = time.monotonic() + 90
    while True:
        # Fresh signature per attempt; the store may still be starting.
        headers = SigV4Signer(settings).sign_headers("PUT", path, payload_sha256=hashlib.sha256(b"").hexdigest())
        try:
            response = httpx.put(f"{endpoint.rstrip('/')}{path}", headers=headers, timeout=30)
            if response.status_code in {200, 409}:
                return
            failure = f"{response.status_code} {response.text[:300]}"
        except httpx.HTTPError as exc:
            failure = repr(exc)
        if time.monotonic() > deadline:
            raise RuntimeError(f"bucket creation failed: {failure}")
        time.sleep(1)


def configure_fake_models(base: str, fake_url: str) -> None:
    with httpx.Client(timeout=30, headers=HEADERS) as client:
        current = _check(client.get(f"{base}/api/settings"))["settings"]
        lmstudio = dict(current.get("lmstudio") or {})
        lmstudio.update({"base_url": fake_url, "model": FAKE_MODEL})
        _check(client.post(f"{base}/api/settings", json={"values": {"provider": "lmstudio", "lmstudio": lmstudio}}))


def chat_round_trip(base: str, other: str) -> dict[str, Any]:
    with httpx.Client(timeout=60, headers=HEADERS) as client:
        session = _check(client.post(f"{base}/api/chat/sessions", json={
            "title": "multihost " + uuid.uuid4().hex[:8],
            "provider_id": "llm:lmstudio",
            "model_id": FAKE_MODEL,
            "read_memory": False,
            "write_memory": False,
        }))
        accepted = _check(client.post(f"{base}/api/chat/sessions/{session['id']}/messages", json={
            "content": "Say hello.",
            "agent_mode": False,
            "user_turn_id": "multihost:" + uuid.uuid4().hex,
            "provider_id": "llm:lmstudio",
            "model_id": FAKE_MODEL,
        }))
        job_id = accepted["job"]["id"]
        deadline = time.monotonic() + 120
        while True:
            job = _check(client.get(f"{other}/api/jobs/{job_id}"))
            job = job.get("job", job)
            if job["status"] in {"completed", "failed", "canceled", "cancelled"}:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("chat job did not finish")
            time.sleep(0.25)
        if job["status"] != "completed":
            raise RuntimeError("chat job failed: " + json.dumps(job.get("error"))[:500])
        messages = _check(client.get(f"{other}/api/chat/sessions/{session['id']}"))["messages"]
    replies = [message for message in messages if message.get("role") == "assistant"]
    if not replies or FAKE_REPLY not in str(replies[-1].get("content")):
        raise AssertionError(f"unexpected chat reply: {replies[-1:]!r}")
    return {"session_id": session["id"], "job_id": job_id}


def submit_probe(client: httpx.Client, base: str, label: str) -> str:
    response = client.post(f"{base}/api/jobs", json={
        "module": "platform",
        "type": "platform.probe",
        "resource_class": "cpu",
        "input_payload": {"duration_ms": 50, "label": label[:64]},
        "compat": {"idempotency_key": label},
    })
    return str(_check(response)["id"])


def wait_jobs(database_url: str, job_ids: list[str], timeout: float) -> dict[str, Any]:
    import psycopg

    deadline = time.monotonic() + timeout
    while True:
        with psycopg.connect(database_url) as connection:
            rows = connection.execute(
                """
                SELECT job.id, job.status,
                       count(*) FILTER (WHERE attempt.status = 'completed'),
                       array_agg(DISTINCT attempt.worker_id) FILTER (WHERE attempt.status = 'completed')
                  FROM omnix_jobs AS job
                  LEFT JOIN omnix_job_attempts AS attempt ON attempt.job_id = job.id
                 WHERE job.id = ANY(%s)
                 GROUP BY job.id, job.status
                """,
                (job_ids,),
            ).fetchall()
        pending = [row[0] for row in rows if row[1] not in {"completed", "failed", "canceled", "cancelled"}]
        if not pending or time.monotonic() > deadline:
            workers = sorted({worker for row in rows for worker in (row[3] or [])})
            return {
                "submitted": len(job_ids),
                "completed": sum(1 for row in rows if row[1] == "completed"),
                "not_completed": [row[0] for row in rows if row[1] != "completed"][:20],
                "duplicate_completions": [row[0] for row in rows if int(row[2]) > 1],
                "distinct_workers": len(workers),
            }
        time.sleep(1)


def events_report_job(base: str) -> dict[str, Any]:
    seen = threading.Event()
    job_box: dict[str, str] = {}

    def listen() -> None:
        with httpx.Client(timeout=httpx.Timeout(30, read=30), headers=HEADERS) as client:
            with client.stream("GET", f"{base}/events") as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    job_id = job_box.get("id")
                    if job_id and job_id in line:
                        seen.set()
                        return

    listener = threading.Thread(target=listen, daemon=True)
    listener.start()
    time.sleep(1)
    with httpx.Client(timeout=30, headers=HEADERS) as client:
        job_box["id"] = submit_probe(client, base, "events-" + uuid.uuid4().hex)
    if not seen.wait(30):
        raise TimeoutError("event stream did not report the submitted job")
    return {"job_id": job_box["id"]}


def asset_across_hosts(upload_host: str, download_host: str) -> dict[str, Any]:
    """Save a manuscript on one host and read it back on another (shared S3)."""
    text = "Multi-host manuscript " + uuid.uuid4().hex
    with httpx.Client(timeout=60, headers=HEADERS) as client:
        saved = _check(client.post(f"{upload_host}/api/assets/story", json={
            "title": "Multihost story",
            "content": text,
            "word_count": 3,
        }))
        asset_id = saved["asset"]["id"]
        downloaded = _check(client.get(f"{download_host}/api/assets/{asset_id}/content"))
    if text not in str(downloaded.get("content")):
        raise AssertionError("downloaded manuscript differs from the saved one")
    return {"asset_id": asset_id, "size_bytes": downloaded.get("size_bytes")}


def live_call_audio(base: str) -> dict[str, Any]:
    from websockets.sync.client import connect

    frames = 0
    pcm = 0
    started = time.perf_counter()
    first_audio_ms = None
    url = base.replace("http", "ws", 1) + "/api/tts/stream/websocket"
    with connect(url, open_timeout=15, close_timeout=5, additional_headers={"Origin": base}) as socket:
        socket.send(json.dumps({"text": "Topology check.", "language": "en", "append_silence": False}))
        while True:
            message = socket.recv(timeout=60)
            if isinstance(message, bytes):
                frames += 1
                pcm += len(message)
                if first_audio_ms is None:
                    first_audio_ms = round((time.perf_counter() - started) * 1000, 2)
                continue
            control = json.loads(message)
            if control.get("type") == "error":
                raise RuntimeError("TTS error: " + str(control.get("message"))[:300])
            if control.get("type") == "done":
                break
    if not frames:
        raise AssertionError("no PCM frames")
    return {"frames": frames, "pcm_bytes": pcm, "first_audio_ms": first_audio_ms}


def run_load(base: str, recorder: Recorder, *, duration: float, threads: int, job_ids: list[str]) -> float:
    stop = time.monotonic() + duration
    lock = threading.Lock()

    def worker(index: int) -> None:
        with httpx.Client(timeout=60, headers=HEADERS) as client:
            sequence = 0
            while time.monotonic() < stop:
                sequence += 1
                recorder.timed("jobs.list", lambda: _check(client.get(f"{base}/api/jobs?limit=20")))
                label = f"load-{index}-{sequence}-{uuid.uuid4().hex[:6]}"
                job_id = recorder.timed("jobs.submit", lambda: submit_probe(client, base, label))
                if job_id:
                    with lock:
                        job_ids.append(job_id)
                recorder.timed("ready", lambda: _check(client.get(f"{base}/ready")))
                if sequence % 10 == 0:
                    recorder.timed("chat.round_trip", lambda: chat_round_trip(base, base))

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        list(pool.map(worker, range(threads)))
    return time.monotonic() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingress", default="http://nginx:8080")
    parser.add_argument("--worker-host", default="http://gateway-worker:8000")
    parser.add_argument("--api-hosts", nargs="+", default=["http://api-1:8000", "http://api-2:8000"])
    parser.add_argument("--fake-models", default="http://fake-models:8020")
    parser.add_argument("--duration-seconds", type=float, default=60)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--output", type=Path, default=Path("artifacts/multihost-topology.json"))
    parser.add_argument("--create-bucket", action="store_true", help="only create the S3 bucket, then exit")
    args = parser.parse_args()
    if args.create_bucket:
        create_bucket()
        return 0

    database_url = os.environ["OMNIX_DATABASE_URL"]
    report: dict[str, Any] = {"measurement": "multihost-topology", "checks": {}, "problems": []}
    hosts = [args.worker_host, *args.api_hosts]
    report["ready"] = {url: data.get("build_revision") if isinstance(data, dict) else data
                       for url, data in wait_ready([*hosts, args.ingress], timeout=300).items()}
    create_bucket()
    configure_fake_models(args.ingress, args.fake_models)

    checks: dict[str, Callable[[], Any]] = {
        "chat_cross_replica": lambda: chat_round_trip(args.api_hosts[0], args.api_hosts[1]),
        "events": lambda: events_report_job(args.ingress),
        "asset_across_hosts": lambda: asset_across_hosts(args.worker_host, args.api_hosts[0]),
        "live_call_audio": lambda: live_call_audio(args.ingress),
    }
    for name, check in checks.items():
        try:
            report["checks"][name] = {"ok": True, **(check() or {})}
        except Exception as exc:
            report["checks"][name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:800]}
            report["problems"].append(f"{name} failed")

    recorder = Recorder()
    job_ids: list[str] = []
    elapsed = run_load(args.ingress, recorder, duration=args.duration_seconds, threads=args.threads, job_ids=job_ids)
    report["load"] = {
        "duration_seconds": round(elapsed, 1),
        "threads": args.threads,
        "operations": recorder.summary(elapsed),
    }
    # Submission is open-loop, so a backlog can remain when the load stops;
    # measure how long the workers take to drain it.
    drain_started = time.monotonic()
    report["jobs"] = wait_jobs(database_url, job_ids, timeout=600)
    report["jobs"]["backlog_drain_seconds"] = round(time.monotonic() - drain_started, 1)
    if report["jobs"]["not_completed"]:
        report["problems"].append("jobs did not all complete")
    if report["jobs"]["duplicate_completions"]:
        report["problems"].append("duplicate job execution")
    if report["jobs"]["distinct_workers"] < 2:
        report["problems"].append("jobs were not spread across both job workers")
    failed_operations = {name: data["errors"] for name, data in report["load"]["operations"].items() if data["errors"]}
    if failed_operations:
        report["problems"].append(f"load errors: {failed_operations}")
    report["result"] = "failed" if report["problems"] else "passed"
    encoded = json.dumps(report, indent=2, sort_keys=True)
    print(encoded)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded + "\n", encoding="utf-8")
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
