# Hermes Metadata Route

Phase 23 target:

- expose a read-only metadata route for Hermes defaults
- return response size limit, timeout bounds, feature flags, and blocked-by-default state
- keep the route hidden from generated OpenAPI until the browser contract is stable
- avoid any execution path or state changes

Runtime route wiring was intentionally left for a later slice if the connector permits the code change.
