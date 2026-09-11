# Local reliability incident

Recorded: 2026-09-11T11:37:09.726658+00:00

Synthetic loopback rehearsal. The candidate worker was configured to return HTTP 503.
The same application bytes are packaged under two fixture versions; this is not an application bug.

| Phase | Measured requests | Failed requests | Error ratio | p95 latency (ms) |
| --- | ---: | ---: | ---: | ---: |
| baseline | 12 | 0 | 0% | 1.273 |
| incident | 4 | 4 | 100% | 1.859 |
| recovery | 12 | 0 | 0% | 6.728 |

## Incident timeline

| Elapsed seconds | Observation |
| ---: | --- |
| 0.060 | baseline_started |
| 1.184 | baseline_verified |
| 1.238 | fault_observed |
| 1.547 | alert_fired |
| 1.547 | recovery_started |
| 1.653 | restored_service_ready |
| 2.175 | alert_cleared |
| 2.791 | recovery_verified |
| 2.793 | cleanup_complete |

Observed fault to alert: 0.309 seconds.
Alert to verified recovery: 1.245 seconds.

## Scope and learning

The monitor records request outcomes and latency, requires sustained breaches, and clears only after healthy windows.
Recovery revalidates the previous package, its health, its reported version and twelve measured requests.
These are timings for one local rehearsal, not production response targets or an aggregate MTTR.
Readiness/version checks are excluded from traffic counts. No traffic is measured during worker transitions.
There is no cloud deployment, persistent-data recovery, live traffic switching, external paging or attestation verification.
The capture is unsigned. File hashes identify bytes and do not authenticate execution.

Cleanup: all owned workers stopped; temporary packages and state removed.
