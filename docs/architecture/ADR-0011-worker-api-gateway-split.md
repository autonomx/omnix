# ADR 0011: Worker and API gateway roles

Status: accepted.

One worker/control gateway per workspace owns background execution through a PostgreSQL advisory lock. API replicas serve requests and may dispatch durably owned chat work, but cannot start singleton monitors, schedulers or recovery. Immutable configuration determines process capabilities; registration declares the required ownership.

The ownership connection is supervised. Loss revokes execution and stops workers; a fresh process acquires the released lock. Startup/shutdown are ordered descriptors. Ingress sends unclassified writes/control to the worker and allowlisted request paths to APIs. Spawned-process tests certify exclusivity, loss, crash and handoff.
