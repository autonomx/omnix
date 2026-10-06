# Agent sandbox

Coding and ops agents run commands and change files on behalf of a person. Omnix
runs every agent that can do so inside a Docker sandbox (WP-4.7).

## Who runs sandboxed

| Run | Isolation |
|---|---|
| Any run with `workspace.edit`, `workspace.write`, `workspace.command` or `workspace.test` (the `coding` and `ops` profiles) | Docker sandbox, whatever isolation it asked for |
| A run that asks for `docker_strong` or `unattended` | Docker sandbox |
| Read-only runs (`research`, `trading-research`, `house`, `personal-assistant`) and review snapshots | Supervised on the host |

The `coding` and `ops` profiles default to `docker_strong`, and a request may
only raise its profile's isolation.

## The sandbox

`python -m app.platform.agent_runtime.sandbox build` builds the image
`omnix-agent-sandbox:pi-0.85.1` from `deploy/docker/agent-sandbox.Dockerfile`:
Node 22 (pinned by digest), git, Python 3 and the Pi coding agent 0.85.1, run
as the non-root `node` user. Projects whose checks need more (a virtualenv, a
database client) build their own image `FROM` it and set
`OMNIX_AGENT_DOCKER_IMAGE`.

Each run gets its own container:

- read-only root file system, `--cap-drop ALL`, `no-new-privileges`;
- memory, CPU and process limits (`OMNIX_AGENT_DOCKER_MEMORY` 4g,
  `OMNIX_AGENT_DOCKER_CPUS` 2, `OMNIX_AGENT_DOCKER_PIDS` 256);
- a 256 MB `noexec` tmpfs at `/tmp`, holding the agent's home (`/tmp/home`):
  the person's home directory never reaches the agent;
- the workspace bind-mounted at `/workspace` (on Linux as the host user's uid);
- only the run's own `OMNIX_AGENT_*` settings and the variables its RunSpec
  allows; the run token is passed by name, never in the command line.

Runs outside the sandbox get a private, per-run home directory too.

## Network

The sandbox joins `omnix-agent-sandbox`, an `--internal` Docker network: it has
no route out. The one container on it with a route out is the relay
(`omnix-agent-broker-relay`, `sandbox_relay.mjs` in the same image), which
forwards only the gateway ports the run uses (the broker and the model
gateway) to the gateway host (`OMNIX_AGENT_SANDBOX_GATEWAY_HOST`, default
`host.docker.internal`). Inside the sandbox the broker is
`http://omnix-agent-broker-relay:<port>/...`; anything else, the internet or
another host port, is unreachable. The broker accepts the run's token only for
that run's broker and model-gateway routes (WP-4.6).

`python -m app.platform.agent_runtime.sandbox check-egress` proves it on a host: from a
container on the sandbox network it must connect to the relay and must fail to
reach `1.1.1.1:443`; it exits 1 otherwise. On Linux the gateway must listen on
an address the Docker bridge reaches (Docker Desktop forwards to loopback).

An operator who manages the network instead sets `OMNIX_AGENT_DOCKER_NETWORK`
(and `OMNIX_AGENT_CONTAINER_BROKER_URL` / `..._MODEL_GATEWAY_URL`), and then
guarantees that network reaches only the broker.

## Commands and approvals

Inside the sandbox, the safe validation commands (`git status`, `git diff`,
`pytest`, `npm test`, `npm run build`, …) run without asking, under the run's
approval policy. Outside it every command asks for approval.

## When Docker is unavailable

A run that needs the sandbox fails with the reason (Docker not installed or
not running, image missing) and how to proceed. To run such agents without
the sandbox instead, set `OMNIX_AGENT_ALLOW_UNSANDBOXED=true`. Each such run:

- runs supervised on the host, with every command asking for approval;
- records an `agent.run.unsandboxed` audit event with the reason;
- shows "Running without the sandbox: every command needs approval" on the
  run in Chat.

`unattended` runs never take the override.

## Folders agents may change

An agent changes a folder in place (a Chat-attached local folder, or a
workspace without a repository) only when it is under
`OMNIX_AGENT_WORKSPACE_ROOTS` (path list; default: the Omnix repository and
`resources/agent_workspaces`). Repository runs work in an Omnix-managed
worktree.

## Concurrency

At most `OMNIX_AGENT_MAX_CONCURRENT_RUNS` agents (default 2) run at once
across every Omnix process: a run takes a leased slot in PostgreSQL before its
agent starts and gives it back when the agent exits (a crashed holder's slot
expires after two minutes). A run waits up to `OMNIX_AGENT_SLOT_WAIT_SECONDS`
(300) for a slot, then fails saying so.

## Verification

- `src/tests/agent_runtime/test_isolation.py`: who is sandboxed, fail-closed
  without Docker, the override, the container flags, home and environment,
  relay URLs, request defaults, the folder allow-list.
- `src/tests/agent_runtime/test_pi_guard_sandbox_approval.py`: the real guard
  extension under Node approves `git status` automatically only when sandboxed.
- `src/tests/agent_runtime/test_agent_sandbox_docker.py`: egress from the
  sandbox network fails except to the relay (needs Docker and the image).
- `src/tests/persistence/test_agent_run_slots_integration.py`: the limit holds
  across two processes; a waiting run starts when a slot frees; a dead
  holder's slot expires.
