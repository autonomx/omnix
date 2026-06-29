# Hermes in top-level setup

`setup.bat` and `setup.sh` now call the Hermes sidecar setup helper as part of the normal one-command setup flow.

To skip that step during local troubleshooting, set:

```bash
OMNIX_SKIP_HERMES_SETUP=1
```

Windows Command Prompt:

```bat
set OMNIX_SKIP_HERMES_SETUP=1
setup.bat
```

Linux, macOS, or WSL2:

```bash
OMNIX_SKIP_HERMES_SETUP=1 bash setup.sh
```

The top-level setup still writes `HERMES_ENABLED=false` by default. Flip it to `true` only after the Hermes sidecar is running and reachable.
