# Service reliability lab

Run a complete synthetic incident: establish a healthy baseline, observe a
candidate returning HTTP 503, detect sustained failure, restore the previous
package and verify recovered traffic. Python 3.12+ is the documented runtime.
The standard library is sufficient; no Azure subscription or credentials are needed.

From the repository root, run this in PowerShell or Bash:

```shell
python reliability_lab.py
```

The command prints its newly created results directory. Exit **0** means the
complete rehearsal passed. Exit **2** means it failed; existing directories are
refused. To choose an explicit new directory:

```shell
python reliability_lab.py --output-dir reports/reliability-first-run
```

## Detection contract

| Setting | Lab value |
| --- | --- |
| Measured endpoint | `/health` on the current owned loopback worker |
| Request spacing | 0.1 seconds after each completed request |
| Rolling window | Last five completed measured requests |
| Breach | Error ratio at least 60%, or nearest-rank p95 latency at least 500 ms |
| Fire | Two consecutive breached full windows |
| Clear | Two consecutive full windows with zero errors and p95 below 500 ms |
| Owner/action | Lab operator: inspect version and health; execute the recovery runbook below |

An unsuccessful response, invalid body or transport failure counts as an error.
Latency includes unsuccessful requests. Windows are sample-based and overlap;
two evaluations do not mean two independent time windows. These thresholds make
a small exercise quick and understandable. They are not production recommendations.

The monitor records state transitions. The harness explicitly executes the
following runbook after the alert; it is not a general automatic remediation agent.

## Recovery runbook

1. Establish twelve healthy requests from fixture version `1.0.0`.
2. Promote fixture `1.1.0` in disposable local state and start its worker with the
   existing harness's HTTP 503 injection. Observe both the failure and version.
3. Collect actual health requests until the sustained-error policy fires.
4. Stop that owned candidate process. Reverify the retained previous ZIP and
   restore it with the existing checksum-only `delivery.rollback` helper.
5. Start the restored worker. Confirm `/health`, `/version` and twelve measured
   requests. Require the alert to clear, and check health and version again.
6. Close the rehearsal only after every owned worker and temporary package is removed.

The incident's injected cause is the worker's `--fail-health` option. Both fixture
versions contain the same application source. The exercise demonstrates detection
and a recovery procedure, rather than diagnosis of an unknown application defect.

## Evidence

| File | Contents |
| --- | --- |
| `samples.jsonl` | Every measured request's status, duration, version label and relative time |
| `incident.json` | Policy, event timeline, phase summaries, environment, source hashes and artifact hashes |
| `incident.md` | Readable incident report with measured outcomes and boundaries |
| `metrics.prom` | A final Prometheus-text snapshot of phase counters and p95 gauges |

`metrics.prom` is a saved export, not a live scrape endpoint or an installed
monitoring stack. Each run has its own counters. Readiness/version probes are
excluded from traffic counts. Worker startup and shutdown gaps are not sampled.

Reported timings are **observed fault to alert** and **alert to verified recovery**.
One rehearsal does not establish an aggregate mean time to recovery, availability
SLO compliance, production alert quality or a performance target.

The application is executed only from a package built by this trusted checkout.
This harness is not a sandbox for arbitrary source. Services run sequentially on
different local ports; no production traffic is switched. There is no cloud
deployment, database recovery, external paging or signature verification here.
The release CLI's attestation policy remains separate and unchanged. Captures are
unsigned; hashes identify bytes without authenticating execution.

## Validation

```shell
python -m unittest discover -s tests -p test_reliability_lab.py -v
```

Tests cover incomplete windows, isolated failures, sustained errors, slow HTTP
successes, clearing, percentile calculation, invalid latencies, existing report
preservation and a real loopback incident. CI exercises the lab on Windows and Linux.

The design follows [Azure Well-Architected incident-management guidance](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/incident-response)
by connecting operational signals, an actionable alert, a documented response
and tested recovery. The small synthetic system makes these boundaries inspectable.
