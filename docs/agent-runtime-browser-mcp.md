# Governed browser and MCP providers

Omnix exposes browser automation and MCP tools to Pi through the existing
`omnix_capability` broker. Pi does **not** receive the raw `agent-browser` or
`mcporter` executables. RunSpec authority, resource scopes, approval policy,
tool budgets, durable execution identity, audit events, and quality acceptance
remain authoritative.

## agent-browser

Install the Vercel Labs CLI on the Omnix worker host and install its browser:

```powershell
.\scripts\setup_agent_tools.ps1
```

The setup helper installs a repo-local Node 24 runtime when the system Node is
older than 24, then installs the pinned `agent-browser` and `mcporter` worker
CLIs. The current MCPorter pin is intentionally held below the worker registry's
release-age window; update it deliberately when the worker policy allows the
newer release.

Omnix auto-detects `agent-browser` on `PATH`. Set
`OMNIX_AGENT_BROWSER_COMMAND` to an absolute executable path when needed.
Set `OMNIX_AGENT_BROWSER_ENABLED=0` to disable the provider.

Browser access is origin constrained. The default allowlist is loopback only:

```text
localhost,127.0.0.1,::1
```

Override it with a JSON list or comma-separated value:

```powershell
$env:OMNIX_AGENT_BROWSER_ALLOWED_DOMAINS='["localhost","127.0.0.1","*.example.test"]'
```

Every invocation uses agent-browser's `--allowed-domains`,
`--content-boundaries`, output limits, a run/session-derived isolated session,
and `--no-webmcp`. The Omnix provider deliberately omits arbitrary JavaScript
`eval`, auth-vault access, profile reuse, state restore, uploads, and downloads.
Those capabilities should only be added later as separately reviewed canonical
capabilities.

The coding profile can be issued:

- `browser.open`
- `browser.snapshot`
- `browser.click`
- `browser.fill`
- `browser.press`
- `browser.hover`
- `browser.select`
- `browser.scroll`
- `browser.wait`
- `browser.get_text`
- `browser.get_attribute`
- `browser.get_url`
- `browser.screenshot`
- `browser.assert_text_contains`
- `browser.assert_attribute_contains`
- `browser.assert_url_contains`
- `browser.close`

The read-only `coding-reviewer` profile has no browser authority.

## MCPorter

MCPorter is an optional worker dependency. It currently requires Node 24+, so
Omnix does not install it as an application npm dependency. Install it on
workers that need MCP access with `scripts/setup_agent_tools.ps1`, or set
`OMNIX_AGENT_MCPORTER_COMMAND` to an absolute executable path.

Set `OMNIX_AGENT_MCP_ENABLED=0` to disable the provider.

MCP authority comes only from the operator-owned policy file. By default Omnix
looks for:

```text
resources/config/agent_mcp_policy.json
```

or a path supplied by `OMNIX_AGENT_MCP_POLICY_PATH`. Start from
`resources/config/agent_mcp_policy.example.json`.

Each tool must declare an Omnix capability id, effect, risk, and approval policy:

```json
{
  "name": "resolve-library-id",
  "capability_id": "mcp.context7.resolve_library_id",
  "effect": "read",
  "risk": "low",
  "approval_policy": "allow_automatic"
}
```

A configured MCP server does not grant Pi authority by itself. A coding task
must compile the corresponding `mcp.*` capability into the RunSpec, and the Pi
broker rejects any other MCP capability id.

For each MCP call Omnix creates an ephemeral MCPorter configuration containing
only the selected policy server and invokes MCPorter with explicit `--config`
and `--root`. This prevents MCPorter's normal project/user config discovery from
turning Cursor, Claude, Codex, or other local MCP configuration into Pi
authority. Agent calls use `--no-oauth`; complete authentication out of band and
expose only the environment keys named by policy.

For HTTP servers, prefer HTTPS. Secrets can be supplied by environment-backed
headers without placing values in the policy:

```json
{
  "headers_from_env": {
    "Authorization": "MY_MCP_AUTH_HEADER"
  }
}
```

For stdio servers, `command` is one executable token and `args` is a separate
argument list. Do not put shell pipelines or composed command strings in the
policy.

## Authority model

```text
Pi
  ├─ workspace tools (read/edit/write/search/test/command)
  └─ omnix_capability
       └─ Omnix broker
            ├─ browser.* -> agent-browser
            ├─ mcp.*     -> MCPorter -> configured MCP server
            └─ github.* / research.* / other existing providers
```

No provider can expand a RunSpec. Provider output is untrusted data, not an
authority grant. New MCP tools require an operator policy change; new browser
behaviors require a canonical capability change.
