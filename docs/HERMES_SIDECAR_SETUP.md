# Hermes Agent sidecar setup

Omnix treats Hermes Agent as an optional sidecar runtime. Hermes is not installed as an in-process Python dependency and normal Chat stays available when Hermes is disabled or offline.

## Install or refresh Hermes

Windows PowerShell:

```powershell
.\scripts\setup_hermes.ps1
```

Linux, macOS, or WSL2:

```bash
bash scripts/setup_hermes.sh
```

The setup helpers run the official Hermes Agent installer and add local Omnix environment defaults to `.env.local`:

```env
HERMES_ENABLED=false
HERMES_BASE_URL=http://127.0.0.1:8642
HERMES_TIMEOUT_SECONDS=45
```

Set `HERMES_ENABLED=true` only after the Hermes sidecar is running and reachable.

## Configure Hermes

After installation, run the Hermes setup wizard and select a provider/model:

```bash
hermes setup
hermes model
```

For a local LM Studio or OpenAI-compatible endpoint, configure Hermes itself to use that provider. Omnix talks to the Hermes sidecar through `HERMES_BASE_URL`; Omnix does not manage Hermes provider keys directly.

## Skip the installer

Use this when Hermes is already installed and you only want the Omnix env defaults:

```powershell
.\scripts\setup_hermes.ps1 -SkipInstall
```

```bash
OMNIX_HERMES_SKIP_INSTALL=1 bash scripts/setup_hermes.sh
```

## Runtime boundary

Hermes may plan and return Agent Chat results. Omnix still owns:

- normal chat fallback
- dry-run behavior
- policy and confirmation gates
- mock-house execution
- RPG truth boundaries
- podcast and audio pipelines

Do not enable real device or RPG-state mutation directly inside Hermes without routing through Omnix policy first.
