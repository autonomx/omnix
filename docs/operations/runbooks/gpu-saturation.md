# GPU saturation and permit starvation

Local model calls take PostgreSQL device permits per model class
(`OMNIX_DEVICE_ID`, `OMNIX_DEVICE_*_CAPACITY`).

## Symptoms

- `OmnixDevicePermitStarvation`: calls wait while the device is full.
- Live calls get HTTP 429 with `Retry-After: 1`; image or TTS jobs queue.

## Dashboards and metrics

- Omnix overview: *Device permits* (held and waiting by model class).
- `omnix_device_permit_held_units` against `omnix_device_permit_capacity_units`;
  `omnix_device_permit_waiting_requests`.
- `/api/diagnostics`: `device_permits` lists holders, queues and the model owner.

## Diagnosis

1. Which model class is full, and who holds it? `/api/diagnostics`
   `device_permits[].holders` (holder ids and lease expiry).
2. A holder that never releases: a hung model call. Its lease expires and is
   reclaimed; check the holding process's logs.
3. Real demand: several long jobs (image generation) competing with
   realtime speech. `OMNIX_DEVICE_*_REALTIME_RESERVED` keeps capacity for
   realtime work.

## Remediation

- Hung holder: restart the process holding the permit; its lease expires
  and the next waiter takes it.
- Demand: queue background GPU work in a dedicated job worker pool, or raise
  realtime reservation. Changing capacity requires draining holders and
  updating the `omnix_device_capacity` row before restart
  ([OPERATIONS: Production worker/API operations](../../OPERATIONS.md#production-workerapi-operations)).

## Verification

- `omnix_device_permit_waiting_requests` returns to 0 between bursts; the
  alert resolves; live calls stop receiving 429.
