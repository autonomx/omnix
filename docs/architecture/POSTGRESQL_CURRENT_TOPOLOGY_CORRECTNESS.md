# PostgreSQL Current-Topology Correctness

Before authority activation, Omnix proves correctness for the process topology it already supports: multiple FastAPI gateways, multiple local workers, event consumers, foreground RPG execution, PostgreSQL, local BlobStore, and deterministic provider fakes in CI.

`omnix_runtime_nodes` is the durable registry for gateway, worker, and event-consumer identity, capabilities, software version, heartbeat, lease expiry, and draining state. A live node identity cannot be overwritten. Expired or stopped identities can be safely reclaimed. PostgreSQL, not process-local memory or Redis, determines current ownership.

The required failure matrix includes gateway crashes before and after commit, worker crashes before lease expiry and after external execution, duplicate HTTP submissions, duplicate outbox delivery, delayed consumers, stale campaign writers, database restart, temporary BlobStore failure, shutdown while work is active, and restart with unpublished events.

Existing job lease, foreground submission, RPG compare-and-swap, outbox inbox, side-effect receipt, and coordinated recovery tests provide the authoritative effect guarantees. Runtime-node tests additionally prove multi-gateway/worker visibility, stale-node recovery, guarded identity reuse, graceful draining, and durable failure evidence. Redis remains absent from all correctness boundaries.