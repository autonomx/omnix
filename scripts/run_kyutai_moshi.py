from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import threading
from pathlib import Path

from app.launcher.huggingface_token_store import load_huggingface_token

_UNMUTE_REPOSITORY = "https://github.com/kyutai-labs/unmute.git"
_UNMUTE_PIN = "c49982eb3aeaf76633dfe4155fa3b8dcb5b3d962"
_DEFAULT_MOSHI_IMAGE = "moshi-server:latest"
_DEFAULT_MIN_FREE_VRAM_MB = 6_144
_STOP_REQUESTED = threading.Event()
_HF_TOKEN_PATTERN = re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")
_TOKEN_ARGUMENT_PATTERN = re.compile(
    r"(?i)(--token(?:=|\s+)|HUGGING_FACE_HUB_TOKEN\s*[=:]\s*|HF_TOKEN\s*[=:]\s*)([^\s\"']+)"
)
_BEARER_PATTERN = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s]+)")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def _request_stop(_signum: int, _frame: object) -> None:
    _STOP_REQUESTED.set()


def _install_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        signal.signal(sigbreak, _request_stop)


def _run_git(git: str, *arguments: str) -> None:
    subprocess.run(
        [git, *arguments],
        check=True,
        timeout=600,
    )


def _ensure_unmute_checkout(unmute_dir: Path) -> Path:
    upstream_compose = unmute_dir / "docker-compose.yml"
    if upstream_compose.is_file():
        return upstream_compose

    auto_bootstrap = os.environ.get("KYUTAI_UNMUTE_AUTO_BOOTSTRAP", "1").strip().lower()
    if auto_bootstrap not in {"1", "true", "yes", "y", "on"}:
        raise RuntimeError(
            "Pinned Unmute checkout was not found and automatic bootstrap is disabled. "
            f"Expected {upstream_compose}."
        )

    if unmute_dir.exists() and any(unmute_dir.iterdir()):
        raise RuntimeError(
            f"Cannot bootstrap Unmute because {unmute_dir} already exists and is not empty. "
            "Set KYUTAI_UNMUTE_DIR to an empty or existing valid checkout."
        )

    git = shutil.which("git")
    if git is None:
        raise RuntimeError(
            "Git was not found. Install Git for Windows or create the pinned Unmute "
            f"checkout manually at {unmute_dir}."
        )

    unmute_dir.parent.mkdir(parents=True, exist_ok=True)
    if unmute_dir.exists():
        unmute_dir.rmdir()
    bootstrap_dir = unmute_dir.with_name(f"{unmute_dir.name}.bootstrap")
    if bootstrap_dir.exists():
        shutil.rmtree(bootstrap_dir)

    print(
        f"[KYUTAI MOSHI] Unmute checkout is missing; cloning pinned commit {_UNMUTE_PIN}...",
        flush=True,
    )
    try:
        _run_git(
            git,
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            _UNMUTE_REPOSITORY,
            str(bootstrap_dir),
        )
        _run_git(
            git,
            "-C",
            str(bootstrap_dir),
            "fetch",
            "--depth",
            "1",
            "origin",
            _UNMUTE_PIN,
        )
        _run_git(
            git,
            "-C",
            str(bootstrap_dir),
            "checkout",
            "--detach",
            _UNMUTE_PIN,
        )
        if not (bootstrap_dir / "docker-compose.yml").is_file():
            raise RuntimeError("The pinned Unmute checkout does not contain docker-compose.yml.")
        bootstrap_dir.replace(unmute_dir)
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        if bootstrap_dir.exists():
            shutil.rmtree(bootstrap_dir, ignore_errors=True)
        raise RuntimeError(
            f"Unable to bootstrap pinned Unmute checkout: {type(exc).__name__}: {exc}"
        ) from exc

    print(f"[KYUTAI MOSHI] Pinned Unmute checkout ready at {unmute_dir}.", flush=True)
    return upstream_compose


def _compose_command(root: Path) -> list[str]:
    unmute_dir = Path(
        os.environ.get("KYUTAI_UNMUTE_DIR", str(root.parent / "unmute"))
    ).expanduser()
    omnix_override = Path(
        os.environ.get(
            "KYUTAI_OMNIX_COMPOSE_FILE",
            str(root / "docker-compose.kyutai-stt.yml"),
        )
    ).expanduser()

    if shutil.which("docker") is None:
        raise RuntimeError("Docker CLI was not found. Start or install Docker Desktop first.")
    upstream_compose = _ensure_unmute_checkout(unmute_dir)
    if not omnix_override.is_file():
        raise RuntimeError(f"Omnix Kyutai compose override was not found: {omnix_override}")

    return [
        "docker",
        "compose",
        "-f",
        str(upstream_compose),
        "-f",
        str(omnix_override),
    ]


def _compose_environment(root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    token = load_huggingface_token(root)
    if token:
        environment["HUGGING_FACE_HUB_TOKEN"] = token
    else:
        environment.pop("HUGGING_FACE_HUB_TOKEN", None)
    environment["KYUTAI_OMNIX_SECURE_ENTRYPOINT"] = str(
        root / "scripts" / "kyutai_moshi_secure_entrypoint.sh"
    ).replace("\\", "/")
    environment.setdefault("OMNIX_KYUTAI_BUILD_JOBS", "2")
    environment.setdefault("OMNIX_KYUTAI_UV_BUILD_JOBS", "1")
    environment.setdefault("OMNIX_KYUTAI_UV_INSTALL_JOBS", "2")
    environment.setdefault("OMNIX_KYUTAI_BUILD_NICE_LEVEL", "10")
    environment.setdefault("OMNIX_KYUTAI_MEMORY_LIMIT", "16g")
    return environment


def _docker_image_exists(environment: dict[str, str]) -> bool:
    image = os.environ.get("KYUTAI_MOSHI_IMAGE", _DEFAULT_MOSHI_IMAGE).strip()
    if not image:
        image = _DEFAULT_MOSHI_IMAGE
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _startup_command(
    base_command: list[str],
    environment: dict[str, str],
) -> tuple[list[str], str]:
    force_rebuild = _flag("KYUTAI_MOSHI_FORCE_REBUILD", "0")
    image_exists = _docker_image_exists(environment)
    if force_rebuild:
        return [*base_command, "up", "--build", "stt"], "forced rebuild requested"
    if not image_exists:
        return [*base_command, "up", "--build", "stt"], "Moshi image is missing"
    return [*base_command, "up", "stt"], "reusing existing Moshi image and container"


def _redact_line(value: str) -> str:
    redacted = _HF_TOKEN_PATTERN.sub("hf_[REDACTED]", value)
    redacted = _TOKEN_ARGUMENT_PATTERN.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
    return _BEARER_PATTERN.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)


def _pump_process_output(process: subprocess.Popen[str]) -> None:
    if process.stdout is None:
        return
    for line in process.stdout:
        print(_redact_line(line), end="", flush=True)


def _gpu_vram_snapshot() -> tuple[int, int, int] | None:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    first_line = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")
    parts = [part.strip() for part in first_line.split(",")]
    if len(parts) != 3:
        return None
    try:
        total_mb, used_mb, free_mb = (int(part) for part in parts)
    except ValueError:
        return None
    return total_mb, used_mb, free_mb


def _minimum_free_vram_mb() -> int:
    raw = os.environ.get("KYUTAI_MOSHI_MIN_FREE_VRAM_MB", str(_DEFAULT_MIN_FREE_VRAM_MB))
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_MIN_FREE_VRAM_MB


def _passes_vram_preflight() -> bool:
    snapshot = _gpu_vram_snapshot()
    if snapshot is None:
        print(
            "[KYUTAI MOSHI] GPU memory preflight unavailable; continuing without a VRAM gate.",
            flush=True,
        )
        return True
    total_mb, used_mb, free_mb = snapshot
    required_mb = _minimum_free_vram_mb()
    print(
        "[KYUTAI MOSHI] GPU before startup: "
        f"{used_mb} MiB used, {free_mb} MiB free, {total_mb} MiB total.",
        flush=True,
    )
    if free_mb >= required_mb:
        return True
    print(
        "[KYUTAI MOSHI] ERROR: refusing to start because only "
        f"{free_mb} MiB of VRAM is free; at least {required_mb} MiB is required. "
        "Unload LM Studio, TTS, image generation, or another GPU workload and retry. "
        "Override with KYUTAI_MOSHI_MIN_FREE_VRAM_MB only after measuring the model safely.",
        flush=True,
    )
    return False


def _stop_service(base_command: list[str], environment: dict[str, str]) -> None:
    print("[KYUTAI MOSHI] Stopping Docker Compose service stt...", flush=True)
    try:
        subprocess.run(
            [*base_command, "stop", "--timeout", "3", "stt"],
            check=False,
            timeout=6,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(
            f"[KYUTAI MOSHI] Could not stop stt cleanly: {type(exc).__name__}: {exc}",
            flush=True,
        )


def main() -> int:
    root = _repo_root()
    try:
        base_command = _compose_command(root)
    except RuntimeError as exc:
        print(f"[KYUTAI MOSHI] ERROR: {exc}", flush=True)
        return 2

    environment = _compose_environment(root)
    if environment.get("HUGGING_FACE_HUB_TOKEN"):
        print(
            "[KYUTAI MOSHI] Hugging Face token configured; gated model downloads are enabled.",
            flush=True,
        )
    else:
        print(
            "[KYUTAI MOSHI] Hugging Face token is not configured. "
            "Enter it in Omnix Launcher Control if the model download requires access.",
            flush=True,
        )

    if not _passes_vram_preflight():
        return 4

    _install_signal_handlers()
    command, startup_reason = _startup_command(base_command, environment)
    print(f"[KYUTAI MOSHI] Startup mode: {startup_reason}.", flush=True)
    print("[KYUTAI MOSHI] Starting: " + " ".join(command), flush=True)
    process = subprocess.Popen(
        command,
        cwd=str(root),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    output_thread = threading.Thread(
        target=_pump_process_output,
        args=(process,),
        daemon=True,
    )
    output_thread.start()

    while process.poll() is None and not _STOP_REQUESTED.wait(0.25):
        pass

    if _STOP_REQUESTED.is_set() and process.poll() is None:
        _stop_service(base_command, environment)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)

    output_thread.join(timeout=2)
    return int(process.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
