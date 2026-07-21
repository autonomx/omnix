# RPG runtime debug logging

The RPG runtime writes local structured diagnostics to:

```text
resources/logs/rpg/
```

The directory is created automatically when the RPG session package or web gateway starts.

## Files

Each file is newline-delimited JSON (`.jsonl`) and uses a UTC date in the filename:

- `activity-YYYY-MM-DD.jsonl` — all RPG events, including HTTP activity, turns, jobs, narration-worker messages, and errors.
- `performance-YYYY-MM-DD.jsonl` — events with measured durations, including turn execution, HTTP requests, and terminal job lifecycle events.
- `errors-YYYY-MM-DD.jsonl` — failed requests, failed jobs, turn failures, Python exceptions, and tracebacks.
- `world-generation-YYYY-MM-DD.jsonl` — compact reusable-world generation and retry diagnostics. This file records run, topic, job, provider route, model, attempts, status, dependency IDs, diagnostic IDs, and bounded error messages. Prompts, completions, provider payloads, generated topic content, and world documents are deliberately omitted.

Every record includes a timestamp, event name, category or level, process ID, and thread name. Relevant records also include `session_id`, `turn_id`, `trace_id`, `duration_ms`, `world_id`, `run_id`, `topic_id`, `job_id`, and structured fields.

## What is captured

The initial instrumentation covers the main gameplay path:

1. Every `/api/rpg/...` request and response, with method, path, status, trace ID, and server duration.
2. Every interactive RPG turn, including player input, action metadata, performance overrides, result type, visible response, session summary, and existing stage timings.
3. Every durable RPG job transition: create/reuse, running, progress, completed, failed, and cancelled.
4. Existing Python `DEBUG`/`INFO`/`WARNING`/`ERROR` records under `app.rpg` and the RPG gateway/job modules. This includes narration-worker activity already emitted through standard logging.
5. Browser or tool telemetry posted to `POST /api/rpg/debug/event`.
6. Reusable-world generation start, exact-run failed retry, worker-pool lifecycle, provider attempts, terminal failures, and pre-provider exceptions in the compact world-generation log.

The general logger intentionally records compact session and result summaries instead of dumping the entire save file on every read. Job payloads and visible turn output are retained up to the configured field-size limit. The dedicated world-generation log is stricter and never records generated canon or provider request/response bodies.

## Inspecting logging status

The hidden diagnostic endpoint returns the active path, retention policy, and current file sizes:

```text
GET /api/rpg/debug/log-status
```

The world-generation endpoint returns the compact log path and format:

```text
GET /api/rpg/world-generation/diagnostics
```

Unexpected generation API errors include a `diagnostic_id` and `diagnostic_log` in the response. Search the compact JSONL file for that ID.

## Configuration

Logging is enabled by default for local RPG runtime use.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `OMNIX_RPG_DEBUG_LOGS` | `1` | Set to `0`, `false`, or `off` to disable RPG file logging. |
| `OMNIX_RPG_LOG_DIR` | `resources/logs/rpg` | Override the output directory. |
| `OMNIX_RPG_LOG_RETENTION_DAYS` | `14` | Delete dated JSONL files older than this many days. |
| `OMNIX_RPG_LOG_MAX_FIELD_CHARS` | `12000` | Maximum length of one string field before truncation in the general RPG logs. |

Keys containing `authorization`, `cookie`, `password`, `secret`, `token`, or `api_key` are replaced with `[redacted]` before writing. The compact world-generation log additionally omits fields whose names indicate prompts, completions, generated content, documents, messages, provider input payloads, or provider output.

## Practical debugging

To inspect the most recent turn in PowerShell:

```powershell
Get-Content .\resources\logs\rpg\activity-$(Get-Date -Format yyyy-MM-dd).jsonl -Tail 50
```

To focus on performance:

```powershell
Get-Content .\resources\logs\rpg\performance-$(Get-Date -Format yyyy-MM-dd).jsonl -Tail 50
```

To copy the latest compact world-generation diagnostics after a failure:

```powershell
Get-Content .\resources\logs\rpg\world-generation-$(Get-Date -Format yyyy-MM-dd).jsonl -Tail 100
```

To find one error returned by the UI:

```powershell
Select-String -Path .\resources\logs\rpg\world-generation-*.jsonl -Pattern 'world-generation-retry-'
```

The same `trace_id` connects the HTTP request records for a request. Turn records have their own turn trace, while `session_id`, `turn_id`, job IDs, run IDs, and diagnostic IDs connect runtime, narration, and job lifecycle activity across files.

These logs can contain player commands, generated narration, session identifiers, and local file paths. Treat the directory as private runtime data and do not commit or publish it without review. The compact world-generation file is designed for easier sharing but should still be reviewed before posting.
