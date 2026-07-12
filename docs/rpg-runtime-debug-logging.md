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

Every record includes a timestamp, event name, category, level, process ID, and thread name. Relevant records also include `session_id`, `turn_id`, `trace_id`, `duration_ms`, and structured fields.

## What is captured

The initial instrumentation covers the main gameplay path:

1. Every `/api/rpg/...` request and response, with method, path, status, trace ID, and server duration.
2. Every interactive RPG turn, including player input, action metadata, performance overrides, result type, visible response, session summary, and existing stage timings.
3. Every durable RPG job transition: create/reuse, running, progress, completed, failed, and cancelled.
4. Existing Python `DEBUG`/`INFO`/`WARNING`/`ERROR` records under `app.rpg` and the RPG gateway/job modules. This includes narration-worker activity already emitted through standard logging.
5. Browser or tool telemetry posted to `POST /api/rpg/debug/event`.

The logger intentionally records compact session and result summaries instead of dumping the entire save file on every read. Job payloads and visible turn output are retained up to the configured field-size limit.

## Inspecting logging status

The hidden diagnostic endpoint returns the active path, retention policy, and current file sizes:

```text
GET /api/rpg/debug/log-status
```

## Configuration

Logging is enabled by default for local RPG runtime use.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `OMNIX_RPG_DEBUG_LOGS` | `1` | Set to `0`, `false`, or `off` to disable RPG file logging. |
| `OMNIX_RPG_LOG_DIR` | `resources/logs/rpg` | Override the output directory. |
| `OMNIX_RPG_LOG_RETENTION_DAYS` | `14` | Delete dated JSONL files older than this many days. |
| `OMNIX_RPG_LOG_MAX_FIELD_CHARS` | `12000` | Maximum length of one string field before truncation. |

Keys containing `authorization`, `cookie`, `password`, `secret`, `token`, or `api_key` are replaced with `[redacted]` before writing.

## Practical debugging

To inspect the most recent turn in PowerShell:

```powershell
Get-Content .\resources\logs\rpg\activity-$(Get-Date -Format yyyy-MM-dd).jsonl -Tail 50
```

To focus on performance:

```powershell
Get-Content .\resources\logs\rpg\performance-$(Get-Date -Format yyyy-MM-dd).jsonl -Tail 50
```

The same `trace_id` connects the HTTP request records for a request. Turn records have their own turn trace, while `session_id`, `turn_id`, and job IDs connect runtime, narration, and job lifecycle activity across files.

These logs can contain player commands, generated narration, session identifiers, and local file paths. Treat the directory as private runtime data and do not commit or publish it without review.
