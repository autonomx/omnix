# Hermes Activity Payload

Phase 15 defines the compact payload shape used by later Hermes activity views.

Fields:

- timestamp
- source
- summary
- names
- dry_run
- ok
- error
- metadata

The payload is intentionally compact so a later storage slice can expose recent items without changing the UI contract.
