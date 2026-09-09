from pathlib import Path

path = Path("src/tests/persistence/test_agent_runtime_repository_integration.py")
text = path.read_text(encoding="utf-8")
marker = "def test_transient_heartbeat_failure_does_not_skip_progress_supervision(monkeypatch) -> None:\n"
if text.count(marker) != 1:
    raise RuntimeError("transient heartbeat regression marker missing or duplicated")
prefix, block = text.split(marker, 1)
needle = "        run_id = f\"agent-heartbeat-transient-{uuid.uuid4().hex}\"\n"
if needle not in block:
    raise RuntimeError("transient heartbeat run id anchor missing")
block = block.replace(
    needle,
    needle + "        worker_id = f\"worker-transient-{uuid.uuid4().hex}\"\n",
    1,
)
count = block.count('worker_id="worker-a"')
if count != 3:
    raise RuntimeError(f"expected three transient worker-a references, found {count}")
block = block.replace('worker_id="worker-a"', 'worker_id=worker_id', 3)
path.write_text(prefix + marker + block, encoding="utf-8")
Path(__file__).unlink()
