# Python runtime dependency inputs

Omnix supports Python 3.11. The generated `*.lock.txt` files are the install
inputs; install them with `--require-hashes` so pip verifies every distribution.

- `requirements.txt` delegates to the gateway lock.
- `dev.lock.txt` adds test and repository tooling.
- `worker.lock.txt` delegates to the gateway lock plus worker-only packages.
- `tts.linux.lock.txt`, `stt.linux.lock.txt` and `image.linux.lock.txt` are
  the Linux installs of the GPU locks for the container images. pip-tools
  writes only the dependencies of the platform it runs on, and Torch and
  `huggingface-hub` have Linux-only dependencies (`nvidia-*`, `triton`,
  `hf-xet`). Compile them in a Linux `python:3.11` container, seeded with the
  Windows lock so the shared pins stay identical: copy `<name>.lock.txt` to
  `<name>.linux.lock.txt`, then run the same `pip-compile` command with that
  output file.
- `tracing.lock.txt` is the gateway lock plus the optional OpenTelemetry
  packages (WP-10.4); `dev.lock.txt` layers on it so the tracing tests run.
- `image.lock.txt`, `tts.lock.txt`, and `stt.lock.txt` contain isolated model
  runtimes. GPU locks use the PyTorch CUDA 12.4 index and pin one Torch version.

Regenerate locks after editing the matching `.in` file with pip-tools 7.6.1.
Use `pip-compile --generate-hashes --output-file requirements/<name>.lock.txt
requirements/<name>.in`; add `--allow-unsafe` for dev and GPU locks. For GPU
locks, also pass `--extra-index-url https://download.pytorch.org/whl/cu124`.
Review the complete resolver diff and validate installations with
`python -m pip install --require-hashes -r requirements/<name>.lock.txt` on
Linux and Windows. The gateway inputs pin Uvicorn's `uvloop` extra behind a
non-Windows platform marker; preserve that hashed entry when compiling from a
Windows environment, where the marker is inactive.

The base install is the gateway runtime. Tests and optional model services use
their own lock files and setup scripts; they are not layered into a single
machine-wide environment.
