# Runbooks

One page per incident type: symptoms, dashboards and metrics, diagnosis,
remediation and verification. Alerts (`deploy/observability/alerts.yml`) name
the symptom; objectives are in [SLOS.md](../SLOS.md) and metrics in
[METRICS.md](../METRICS.md).

| Runbook | Alerts |
|---|---|
| [Worker ownership lost](worker-ownership-lost.md) | `OmnixOutboxLagging`, `OmnixScheduledTaskFailing` |
| [Stuck jobs or queue growth](stuck-jobs.md) | `OmnixInteractiveQueueStalled`, `OmnixBackgroundQueueStalled`, `OmnixExpiredLeasesNotRecovered`, `OmnixDeadLetters` |
| [PostgreSQL outage](postgresql-outage.md) | `OmnixJobSnapshotFailing`, `OmnixDatabasePoolWaiting`, `OmnixErrorBudgetFastBurn` |
| [GPU saturation and permit starvation](gpu-saturation.md) | `OmnixDevicePermitStarvation` |
| [Provider outage and open circuit](provider-outage.md) | `OmnixProviderFailing`, `OmnixProviderCircuitOpen` |
| [Sign-in outage (OIDC)](auth-outage.md) | `OmnixAuthUnavailable`, `OmnixAuthRejectionSpike` |
| [Disk full or retention failing](disk-full.md) | `OmnixScheduledTaskFailing` |
| [Secret rotation](secret-rotation.md) | (scheduled, or after a leak) |
| [Rolling upgrade and rollback](rolling-upgrade.md) | (planned change) |
| [Restore](restore.md) | (recovery) |

Before restarting or cleaning anything in an incident, keep the identifiers
and logs that explain it (session, job or run id, request id, timestamps); see
[OPERATIONS: PostgreSQL and recovery](../../OPERATIONS.md#postgresql-and-recovery).
