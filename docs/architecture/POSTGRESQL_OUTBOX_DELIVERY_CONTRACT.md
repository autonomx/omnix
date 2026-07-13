# PostgreSQL Outbox and Side-Effect Delivery Contract

Omnix uses a transactional outbox for recoverable at-least-once delivery. A domain change and its outbox event commit in the same PostgreSQL transaction. Consumers must be idempotent and may not treat process-local acknowledgement as durable completion.

## Event envelope

Every new outbox record contains:

- a globally unique `event_key`;
- event `schema_version`;
- workspace, aggregate type, and aggregate ID;
- event type;
- optional ordering key and monotonic aggregate sequence;
- optional correlation and causation IDs;
- occurrence, availability, creation, publication-attempt, and publication timestamps;
- bounded attempt state and error metadata;
- a JSON payload.

Events with the same ordering key are published one unpublished event at a time. Unrelated ordering keys remain independently claimable.

## Publisher claims

Publishers use bounded leases and `FOR UPDATE SKIP LOCKED`. A crashed publisher leaves a recoverable expired claim. Publication completion is guarded by the event ID and claim token. Retry clears the claim and schedules a future availability time.

A poison event can be moved to `omnix_outbox_dead_letters` without blocking unrelated ordering keys.

## Consumer inbox

`omnix_outbox_consumer_inbox` is the durable per-consumer deduplication boundary.

- first delivery creates a processing claim;
- a completed delivery returns the previously stored result;
- an active unexpired processing claim is busy and cannot be stolen;
- an expired processing claim or failed claim can be recovered;
- repeated failures can move the consumer/event pair to a dead letter;
- explicit replay removes a terminal inbox record before redelivery.

A consumer that crashes after applying its domain effect but before transport acknowledgement must still complete or recover through the inbox record rather than applying the effect twice.

## External side effects

Externally visible operations use `omnix_side_effect_receipts` keyed by workspace, effect scope, and idempotency key. Reusing a key with the same request returns the existing status or result. Reusing a key with a different request hash fails closed.

Provider calls, webhooks, remote dispatch, notifications, and asset-publication effects occur after the authoritative transaction commits. The outbox or durable job record supplies their idempotency key.

## Replay and retention

Replay is explicit and consumer-scoped. It must not silently erase completion records. Retention may remove terminal inbox and outbox records only after the configured replay, audit, and idempotency windows have elapsed.

## Verification

Provider-free PostgreSQL integration tests cover:

- transaction rollback of outbox writes;
- ordered claims;
- expired-claim recovery;
- retry and publication guards;
- completed-delivery deduplication;
- explicit replay;
- poison-event quarantine;
- side-effect result reuse and mismatched-request rejection.
