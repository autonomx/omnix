# Omnix Setup Guide

## Gateway roles and deployment inputs

The normal development launcher can run `python scripts/run_omnix_gateway.py --api-replicas 2`, supervising one worker and two API processes. Each process binds a validated frozen runtime configuration before loading features. Configure authoritative `OMNIX_DATABASE_URL` and use the existing PostgreSQL setup below; production never falls back to SQLite or memory.

| Input | Meaning |
| --- | --- |
| `OMNIX_GATEWAY_BACKGROUND_ROLE=worker` or `api` | Worker owns singleton background execution; API serves requests under durable chat ownership. Default is worker. |
| `OMNIX_TTS_URL`, `OMNIX_STT_URL`, `OMNIX_IMAGE_URL` | HTTP(S) compute service endpoints without credentials/query/fragment. APIs use configured TTS remotely. |
| `OMNIX_GATEWAY_TTS_HTTP=1` | Worker also uses HTTP TTS; requires a TTS endpoint. |
| `OMNIX_GATEWAY_REQUIRED_WORKERS` | Comma-separated workers required for readiness; unhealthy/mock required workers prevent readiness. |
| `OMNIX_GATEWAY_API_ORIGINS` | Up to eight distinct API origins, for diagnostics and local routing. |
| `OMNIX_SOFTWARE_REVISION` | Build identifier in runtime diagnostics and durable node registration. |
| `OMNIX_SERVICE_TOKEN` | Shared URL-safe service credential with at least 32 random bytes; the local launcher provisions protected storage when unset. Required on all non-health model-service routes and internal worker requests. |
| `OMNIX_MAX_UPLOAD_BYTES` | Positive integer; streamed model-service request budget, default 52428800 bytes including multipart overhead. |
| `VITE_ASSISTANT_STT_URL=/api/stt?authority=auto` | Browser speech routes through its gateway origin. The gateway sends the private credential to `OMNIX_STT_URL`. |

Optional explicit `OMNIX_GATEWAY_OWNS_BACKGROUND_RUNTIME` and `OMNIX_GATEWAY_ALLOW_LOCAL_TTS` flags must agree with the derived topology. API replicas cannot instantiate local CUDA TTS. Keep speech worker-routed without a remote endpoint, or configure the shared service on every API process. For production, build the web app and install [the Nginx ingress example](architecture/OMNIX_PRODUCTION_INGRESS.md); the Vite proxy is for local development. See [operations](OPERATIONS.md) for readiness/recovery and [architecture gates](testing/ARCHITECTURE_GATES.md) for disposable test database and certification commands.

This guide covers a local developer/operator setup for the current Omnix application: PostgreSQL, Python backend, React web app, optional model workers/providers, Hermes, and the Windows launcher.

## 1. Prerequisites

Install the tools needed for the parts of Omnix you intend to run.

### Required for the core web application

- Git.
- A modern Python supported by the repository dependencies.
- `pip` and a Python virtual environment or Conda environment.
- Node.js/npm compatible with the repository's Vite 7 toolchain.
- Docker Desktop or another Docker-compatible runtime for the provided local PostgreSQL service.

### Optional depending on features

- NVIDIA CUDA-capable GPU and the repository's matching PyTorch build for local image/TTS/other GPU models.
- LM Studio or another configured LLM provider.
- Dedicated TTS and STT environments/services.
- Hermes Agent for optional agent-sidecar workflows.
- Hugging Face credentials for gated/private model downloads where a selected model requires them.
- Provider credentials for remote AI, market-data, Google/GitHub, or other configured integrations.
- TP-Link Kasa/Tapo devices on the local network for smart-home capability testing.

## 2. Clone the repository

```bash
git clone <your-omnix-repository-url>
cd omnix
```

Do not commit local secrets, model credentials, provider tokens, or database passwords.

## 3. PostgreSQL

PostgreSQL is the authoritative structured-data runtime database. SQLite is not a supported runtime replacement.

### Start the provided local database

The repository includes `docker-compose.postgres.yml` using PostgreSQL 17.

For a disposable local-development setup you can use the compose defaults:

```bash
docker compose -f docker-compose.postgres.yml up -d
```

The defaults are:

```text
host:     127.0.0.1
port:     5432
user:     omnix
database: omnix
container: omnix-postgres
```

The compose file also has a default development password. For any environment beyond a throwaway local workstation, set an explicit `OMNIX_POSTGRES_PASSWORD` before provisioning the container.

Example with explicit credentials:

```bash
export OMNIX_POSTGRES_USER=omnix
export OMNIX_POSTGRES_DB=omnix
export OMNIX_POSTGRES_PASSWORD='replace-with-a-strong-local-password'
docker compose -f docker-compose.postgres.yml up -d
```

PowerShell:

```powershell
$env:OMNIX_POSTGRES_USER = 'omnix'
$env:OMNIX_POSTGRES_DB = 'omnix'
$env:OMNIX_POSTGRES_PASSWORD = 'replace-with-a-strong-local-password'
docker compose -f docker-compose.postgres.yml up -d
```

### Configure `OMNIX_DATABASE_URL`

Backend persistence reads a PostgreSQL URL from `OMNIX_DATABASE_URL` and rejects non-PostgreSQL runtime URLs.

Example:

```bash
export OMNIX_DATABASE_URL='postgresql://omnix:replace-with-a-strong-local-password@127.0.0.1:5432/omnix'
```

PowerShell:

```powershell
$env:OMNIX_DATABASE_URL = 'postgresql://omnix:replace-with-a-strong-local-password@127.0.0.1:5432/omnix'
```

If the password contains URL-special characters, URL-encode it in the DSN.

### Windows protected credential flow

The Windows launcher supports a user-protected PostgreSQL URL instead of keeping the active DSN in a general settings file.

After the `omnix-postgres` container has been provisioned with the desired credentials:

```powershell
.\scripts\manage_postgresql_credential.ps1 -Action provision-from-container
```

Check the protected credential:

```powershell
.\scripts\manage_postgresql_credential.ps1 -Action status
```

`start_all.bat` uses the script's `launch` path to inject `OMNIX_DATABASE_URL` into the launched Omnix process.

### Apply and verify migrations

With `PYTHONPATH=src` and `OMNIX_DATABASE_URL` set:

```bash
python -m app.persistence health
python -m app.persistence migrate
python -m app.persistence verify
```

You can inspect migration state without applying changes:

```bash
python -m app.persistence status
```

The persistence CLI also contains backup/restore and coordinated-recovery commands for operator workflows. Run the CLI help before using destructive or recovery-oriented operations:

```bash
python -m app.persistence --help
```

## 4. Python backend environment

Create/activate your environment, then install the base dependencies:

```bash
pip install -r requirements.txt
```

The requirements include FastAPI/Uvicorn/Pydantic, PostgreSQL drivers, audio/document-processing dependencies, optional image-model libraries, local Kasa support, and the Python test stack.

### GPU/PyTorch note

`requirements.txt` intentionally does not pin/install the repository's CUDA PyTorch build. The repository comments currently target the CUDA 12.4 family and direct Windows GPU setup through `scripts/requirements/bootstrap_omnix_flux_env.ps1`.

For the GPU-enabled Windows environment, prefer the repository bootstrap rather than letting a generic dependency install silently replace PyTorch:

```powershell
.\scripts\requirements\bootstrap_omnix_flux_env.ps1
```

Review the script before running it on a machine with an existing customized ML environment.

## 5. Frontend dependencies

Install the root npm workspace:

```bash
npm install
```

Useful frontend commands:

```bash
npm run web:dev
npm run web:typecheck
npm run web:test
npm run web:test:e2e
npm run web:build
npm run web:preview
```

The supported browser application is `src/apps/web`.

## 6. Start the gateway

Make sure the Python environment is active, `PYTHONPATH` includes `src`, the database is reachable, and required provider/service environment variables are set.

Linux/macOS/WSL:

```bash
export PYTHONPATH=src
python -m uvicorn app.gateway.main:app --host 127.0.0.1 --port 8000
```

PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python -m uvicorn app.gateway.main:app --host 127.0.0.1 --port 8000
```

Verify:

```text
http://127.0.0.1:8000/api/health
```

The gateway also exposes runtime/worker status and the shared `/events` stream used by the web app.

## 7. Start the web app

In another terminal:

```bash
npm run web:dev
```

Open:

```text
http://localhost:5173/
```

The Vite development server proxies `/api` and `/events` to `http://127.0.0.1:8000`.

A healthy core development setup therefore looks like:

```text
5173  Omnix React/Vite web app
8000  Omnix FastAPI gateway
5432  PostgreSQL (default local port)
```

## 8. Configure an LLM provider

Omnix uses its shared provider registry rather than a chat-specific provider stack. Configure providers through the application Settings/Providers surfaces and the relevant environment/configuration fields.

### LM Studio token

If LM Studio requires API authentication, set `LM_API_TOKEN` before starting the backend:

```bash
export LM_API_TOKEN='your-lm-studio-token'
```

PowerShell:

```powershell
$env:LM_API_TOKEN = 'your-lm-studio-token'
```

The LM Studio provider sends it as a Bearer token. Provider configuration can also supply an API key through the provider settings contract.

Do not put real API keys in documentation, committed source files, screenshots, or test fixtures.

## 9. Optional local model services

Omnix can split model workloads across services/environments. The current Windows launcher is configured around these default loopback ports:

| Service | Default URL/port |
| --- | --- |
| Gateway | `http://127.0.0.1:8000` |
| Launcher dashboard | `http://127.0.0.1:5055` |
| TTS | `http://127.0.0.1:5101` |
| STT | `http://127.0.0.1:5201` |
| Image | `http://127.0.0.1:5301` |
| Hermes | `http://127.0.0.1:8642` |

Environment variables used by the launcher/runtime include:

```text
OMNIX_TTS_URL
OMNIX_STT_URL
OMNIX_IMAGE_URL
OMNIX_GATEWAY_URL
HERMES_BASE_URL
```

```omnix-diagram service-topology
```

The exact worker startup command depends on the local environment and model installation. The important contract is that the configured service URL is reachable and reports the capability/readiness expected by the provider registry.

### Image service and model residency

The default Windows launcher starts the lightweight image service without preloading the heavyweight image model:

```text
OMNIX_IMAGE_ENABLED=1
OMNIX_START_IMAGE_SERVICE=1
OMNIX_IMAGE_PRELOAD=0
OMNIX_IMAGE_WARMUP=0
OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD=1
```

Use the Image Generation workspace to download (if necessary), explicitly load, and unload the selected model. A running image service does not mean model weights are resident in VRAM.

## 10. Hermes Agent sidecar

Hermes is optional and out of process. Normal Chat remains usable when Hermes is disabled/offline.

Windows PowerShell:

```powershell
.\scripts\setup_hermes.ps1
```

Linux/macOS/WSL2:

```bash
bash scripts/setup_hermes.sh
```

The helpers write local defaults similar to:

```env
HERMES_ENABLED=false
HERMES_BASE_URL=http://127.0.0.1:8642
HERMES_TIMEOUT_SECONDS=45
```

Configure Hermes itself:

```bash
hermes setup
hermes model
```

Only set `HERMES_ENABLED=true` after the sidecar is reachable. See [HERMES_SIDECAR_SETUP.md](HERMES_SIDECAR_SETUP.md) for the runtime boundary and skip-install options.

## 11. Windows launcher dashboard

`start_all.bat` is the repository's integrated Windows operator launcher. It:

- checks Docker and the `omnix-postgres` container;
- loads the protected PostgreSQL credential;
- verifies persistence connectivity;
- configures the launcher/gateway and worker URLs;
- configures live-agent/Hermes, Kasa, image-service, and diagnostic defaults;
- starts the launcher dashboard on port `5055`;
- asks the launcher to start the gateway and waits for gateway health;
- can open the application/launcher pages in a browser.

Run:

```powershell
.\start_all.bat
```

### Important portability note

The current batch file contains workstation-specific absolute Python/Conda paths for the `rpg-flux`, `rpg-tts`, and `rpg-stt` environments. Treat it as an operator configuration template unless your workstation matches those paths. Update or replace those paths for your machine rather than assuming the batch file is portable unchanged.

Useful launcher-related environment values include:

```text
OMNIX_APP_OPEN_URL
OMNIX_LAUNCHER_URL
OMNIX_LAUNCHER_AUTO_START
OMNIX_LAUNCHER_OPEN_BROWSER
OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS
OMNIX_BLOB_ROOT
```

`OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS` defaults to 420 seconds. The launcher
uses it for gateway readiness checks, and the Windows startup watchdog retries
the web service after gateway health succeeds. Increase it for unusually slow
first boots that import or warm large local runtime dependencies.

## 12. Optional Kasa/Tapo smart-home integration

The Windows launcher defines local defaults for TP-Link Kasa discovery/control:

```text
OMNIX_KASA_ENABLED=1
OMNIX_KASA_DISCOVERY_TARGET=255.255.255.255
OMNIX_KASA_TIMEOUT_SECONDS=4
OMNIX_KASA_DEVICE_HOST=
OMNIX_KASA_DEVICE_ALIAS=
```

`python-kasa` is a backend dependency. Credentials, if required for a device family, should be passed through the appropriate local credential/environment path rather than committed to source.

Smart-home actions are governed assistant capabilities; enabling the network adapter does not bypass capability/approval policy.

## 13. Trading and market-data configuration

Trading charts/research depend on configured market-data providers. Use Settings → Trading & Market Data for provider credentials and feature defaults where available.

Examples of current configuration/use include:

- canonical stock/crypto instruments and provider bindings;
- CoinMarketCap-oriented market-data configuration in Settings;
- read-only authoritative market quote capabilities such as Alpaca IEX when configured;
- feature-specific scanner/replay/research/catalyst data services.

Do not assume that enabling market data grants live broker/order authority. Paper simulation and read-only data are distinct from real broker mutation.

## 14. Web research configuration

Settings → Assistant & Chat exposes research-related defaults including:

- default research mode;
- primary web-search provider;
- fallback provider priority;
- research budgets;
- runtime/provider status.

Research integrations may require credentials depending on the configured provider. Keep provider secrets outside browser local state and source control.

## 15. Build and validate

### Frontend

```bash
npm run web:typecheck
npm run web:test
npm run web:test:e2e
npm run web:build
```

### Generated API contracts

```bash
npm --workspace @omnix/web run api:generate
npm --workspace @omnix/web run api:check
```

### Python

Run the relevant focused tests during development and the broader suite before merging:

```bash
pytest
```

Agent-runtime, trading, RPG, persistence, provider, and browser/e2e areas also have dedicated test scripts/suites in `scripts/` and `src/tests/`.

### Database verification

```bash
python -m app.persistence verify
```

## 16. Common troubleshooting

### Browser shows API errors / Vite reports `ECONNREFUSED`

Check the gateway first:

```text
http://127.0.0.1:8000/api/health
```

If it is down, start the FastAPI gateway before debugging the browser app.

### PostgreSQL startup fails

Check:

```bash
docker ps
docker logs omnix-postgres
```

Then verify the DSN and migrations:

```bash
python -m app.persistence health
python -m app.persistence status
python -m app.persistence verify
```

### Backend says SQLite is unsupported

Set `OMNIX_DATABASE_URL` to a `postgresql://...` URL. PostgreSQL is the supported structured runtime backend.

### LM Studio returns unauthorized

Set `LM_API_TOKEN` or the provider API-key configuration and restart/reload the provider as appropriate.

### Image Generation says model unloaded

That is expected with explicit-load mode. Use Image Generation to download/check the model and load weights before submitting a generation job.

### Image worker is unavailable

Check `OMNIX_IMAGE_ENABLED`, `OMNIX_IMAGE_URL`, the worker process, and Settings/Diagnostics runtime status.

### TTS/STT work remains queued or fails

Check that the service URL is configured and the corresponding worker/provider reports healthy. Voice and STT jobs use dedicated GPU resource classes and require the matching service environment.

### Hermes features are unavailable

Keep normal Chat running, then verify:

```text
HERMES_ENABLED=true
HERMES_BASE_URL=http://127.0.0.1:8642
```

and ensure the Hermes sidecar itself is running/configured.

### Smart-home device is not found

Verify local-network reachability, `python-kasa`, the discovery target, device credentials if applicable, and any explicitly pinned host/alias.

### Frontend types are stale after an API change

Regenerate and check the OpenAPI-derived client/types:

```bash
npm --workspace @omnix/web run api:generate
npm --workspace @omnix/web run api:check
```

## 17. Production/operator considerations

Omnix is designed local-first, but the same rules apply when services are split across machines:

- bind public services intentionally; development defaults use loopback;
- use strong database credentials;
- terminate TLS and authenticate any non-loopback service exposure;
- isolate model workers and secrets appropriately;
- keep PostgreSQL backups coordinated with blob/artifact backups;
- use the persistence backup/recovery tooling and verify restore procedures;
- do not expose unrestricted agent workspace/broker capabilities to untrusted networks;
- keep destructive tool actions behind explicit approval and scope controls.

For the deeper component model, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Listener defaults

Omnix-managed listeners bind to `127.0.0.1`. `OMNIX_BIND_HOST` selects the address;
any non-loopback address also requires `OMNIX_ALLOW_LAN=true`. The launcher
passes the validated address to gateway, web, STT, TTS and image services.
Legacy `OMNIX_TTS_HOST` and `OMNIX_GATEWAY_HOST` listener settings are replaced
by `OMNIX_BIND_HOST`. The standalone compatibility API uses port `8101`
(`OMNIX_OPENAI_API_PORT` overrides it), leaving `8001` available for API replicas.

For an explicitly exposed Vite listener, set `OMNIX_BIND_HOST=0.0.0.0` and
`OMNIX_ALLOW_LAN=true` before running `npm --prefix src/apps/web run dev:lan`
or `npm --prefix src/apps/web run preview:lan`. Add the browser's exact origin
to `OMNIX_ALLOWED_ORIGINS` and hostname to `OMNIX_ALLOWED_HOSTS`. Allowed CORS
origins default to localhost and 127.0.0.1 on ports 5173 and 4173. Wildcards
are rejected. Configure an authenticated ingress before exposing a deployment.

The gateway, launcher and model services validate `Host` for every request.
`OMNIX_ALLOWED_HOSTS` extends the default localhost and loopback allow-list.
Every POST, PUT, PATCH and DELETE requires `X-Omnix-Client` (for example `web`,
`gateway` or `cli`); browser mutation and WebSocket origins must be explicitly
allowed. The web client and launcher UI add the header automatically.
