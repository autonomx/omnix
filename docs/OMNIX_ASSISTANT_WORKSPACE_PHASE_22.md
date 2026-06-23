# Omnix Assistant Workspace Phase 22 — Transcript Integration

Phase 22 adds transcript segment contracts for live input text.

## Scope

- Model partial and final transcript segments.
- Join final transcript text deterministically.
- Replace partial transcript segments without mutating the original list.

## Acceptance criteria

- Partial transcript text is excluded from final transcript output.
- Partial replacement is deterministic.
- Helpers are independent of external services.
