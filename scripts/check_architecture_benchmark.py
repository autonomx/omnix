"""Reject material benchmark regressions while allowing noisy CI timings."""
import argparse
import json
from pathlib import Path


def regressions(baseline, measured):
    failures = []
    for name in ('health_during_job_read', 'event_loop_lag_during_sse_poll'):
        for percentile in ('p95_ms', 'p99_ms'):
            # A blocking 50ms store call should never make health/event-loop
            # latency grow to that delay; absolute allowance absorbs CI noise.
            ceiling = max(40, baseline[name][percentile] * 5)
            if measured[name][percentile] > ceiling:
                failures.append(f'{name}.{percentile} exceeds {ceiling:.1f}ms')
    if measured.get('error_count', 0) or measured.get('active_requests_at_end', 0):
        failures.append('Errors or requests remained after the benchmark')
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--measured', type=Path, required=True)
    args = parser.parse_args()
    failures = regressions(json.loads(args.baseline.read_text(encoding='utf-8')),
                           json.loads(args.measured.read_text(encoding='utf-8')))
    if failures:
        parser.error('; '.join(failures))
    print('Architecture benchmark is within the regression allowance')


if __name__ == '__main__':
    main()
