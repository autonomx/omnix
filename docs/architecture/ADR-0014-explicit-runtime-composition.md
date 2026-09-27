# ADR 0014: Explicit runtime dependency composition

Status: accepted.

Production selects repositories through explicit cached factories and a typed `GatewayRuntimeServices` container. Domain constructors accept injected repositories; document consumers use a frozen callback service container. Request transactions remain in the existing unit of work.

Do not replace feature exports or mutate standard-library SQLite functions during bootstrap. The reduced installer temporarily retains only the shared document callback registration, with a reviewed deletion plan. Existing adapters remain where they preserve real domain contracts. This incrementally removes hidden import-order dependencies without creating a generic dependency-injection framework or duplicate persistence authority.
