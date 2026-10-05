# Adding an agent capability

A capability is one governed action (`acme.lookup`) that agents, chat tools,
TaskGraph nodes and workflows can request. Adding one takes one declaration
and one adapter registration. Profile ceilings decide which agents may be
issued it. `src/tests/agent_runtime/test_extension_recipe.py` follows these
steps with a fake capability and proves the result.

## 1. Declare it

Add a row to the capability list in `src/app/capabilities/registry.py`:

```python
_cap(
    "acme.lookup",                  # <namespace>.<action>; the namespace is the tool id
    "Look up an Acme record",
    "Read one Acme record by id.",
    zone="broker",                  # where it runs: worker, broker, model or context
    effect="read",                  # read, create, mutate, delete or execute
    network=True,
    connection=True,                # needs a connected account before it runs
    provider="Acme",
    category="productivity",
    assistant=True,                 # shown in the assistant tool settings
    input_schema={"record_id": "string"},
),
```

The declaration is the authority record. From it Omnix derives:

- the assistant tool and its settings entry (`assistant_tools/registry.py`,
  `config_store.py`); a new tool is off until the operator enables it;
- the approval policy: `effect`, `risk`, `confirmation` and `destructive`
  pick `allow_automatic`, `ask_sensitive` or `always_ask` unless `approval=`
  sets it;
- the review gate (`assistant_tools/gate.py`), which refuses unknown tools
  and actions, disabled tools, missing connections and unapproved calls.

## 2. Register the adapter

Write the function that performs the action and returns an
`AssistantToolResult`, and add it under the namespace in `ADAPTERS` in
`src/app/platform/assistant_tools/executor.py`:

```python
def run_acme_tool_request(request: AssistantToolRequest) -> AssistantToolResult:
    ...

ADAPTERS = MappingProxyType({
    ...,
    "acme": run_acme_tool_request,
})
```

The registry is fail-closed: a declared capability without an adapter returns
`unknown_adapter` and changes nothing. Adapters run only after the gate has
reviewed the request against the current tool policy; they never decide
authority themselves.

## 3. Let agents use it (optional)

Agent runs receive capabilities only within their profile's ceiling
(`src/app/platform/agent_runtime/profiles.py`). To let a profile be issued the new
capability, add it to that profile's `external_capabilities` (always issued)
or `optional_external_capabilities` (issued when the task needs it). Profiles
are ceilings, not grants: a request for a capability outside the ceiling is
refused when the run is compiled.

Profile behaviour is also declared there: `produces_diff`,
`repository_guidance`, `operator_mcp_tools`, `requires_workspace` and
`isolation_policy`. Runtime code reads these attributes; it does not compare
profile ids.

## Checklist

- The declaration's `effect` and `risk` match what the adapter can change.
- The adapter validates its input and reports `state_changed` truthfully.
- A test covers the adapter's success and refusal paths.
- `python -m pytest src/tests/agent_runtime/test_extension_recipe.py` passes.
