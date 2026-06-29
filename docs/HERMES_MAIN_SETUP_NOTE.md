# Hermes in top-level setup

`setup.bat` and `setup.sh` call the Hermes sidecar setup helper as part of the normal one-command setup flow.

Default behavior is install-only. The Hermes package is installed or refreshed, Omnix writes safe `.env.local` defaults, and the Hermes first-run wizard is skipped.

To configure Hermes later, run:

```bash
hermes setup
hermes model
```

To skip the Hermes step during local troubleshooting, set:

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

To opt into the interactive Hermes wizard during setup, set:

```bash
OMNIX_HERMES_SETUP_MODE=interactive
```

The top-level setup still writes `HERMES_ENABLED=false` by default. Flip it to `true` only after the Hermes sidecar is configured, running, and reachable.
