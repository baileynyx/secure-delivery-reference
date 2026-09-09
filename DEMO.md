# Five-minute demo: a release fails, recovery is verified

**Independent engineering demonstration by Bailey Fitchett · Python · GitHub Actions · Delivery reliability**

This exercise runs locally built packages as disposable loopback HTTP services. It demonstrates successful release checks, rejection of a tampered artifact, and restoration of the previous verified release after an injected health failure.

## Prepare once

Use Git and Python 3.11 or later; CI uses Python 3.12. The demo needs permission to create child processes and bind unused loopback ports. It requires no Python packages, Docker, cloud account or credentials.

The following commands work in PowerShell or Bash:

```shell
# Clone a separate copy and enter the root containing the release tools.
git clone https://github.com/baileynyx/secure-delivery-reference.git secure-delivery-demo
cd secure-delivery-demo

# Validate packaging, HTTP behavior, rejection, recovery and process cleanup.
python -m unittest discover -s tests -v
```

Expected: 13 tests pass and the final result is `OK`. Complete setup before presenting. If a restricted environment blocks loopback or child processes, use the hosted evidence rather than claiming a local run succeeded.

## 0:00–0:45 — Explain the release contract

Open [delivery.py](delivery.py): `build` creates a deterministic allowlisted ZIP, `verify` checks its bytes against an expected SHA-256 and validates its manifest, `promote` records the candidate and previous release, and `rollback` reverifies the retained previous package before restoring its record.

The existing promotion command records state only. The new [failure_demo.py](failure_demo.py) harness adds temporary worker startup, HTTP observations and failure-triggered recovery for this exercise. It executes packages built from this checkout; it is not a sandbox for untrusted code.

## 0:45–2:00 — Run the experiment

```shell
# Build disposable fixtures, exercise real loopback HTTP requests and retain
# observed results after all worker processes, temporary state and ZIPs are removed.
python failure_demo.py --output-dir reports/failure-demo
```

The command prints JSON and writes `reports/failure-demo/evidence.json` and `evidence.md`. Success exits 0 and reports `"result": "passed"`; an unexpected error exits nonzero. If checking manually, inspect `$LASTEXITCODE` in PowerShell or `$?` in Bash immediately after the command. Check the exit code and completion timestamp before treating an existing report as evidence of a new run.

## 2:00–3:30 — Read the observations

| Stage | Expected evidence | Why it matters |
| --- | --- | --- |
| Establish 1.0.0 | `/health` returns 200/`ok`; `/version` returns 200/`1.0.0` | Establishes a verified baseline package and observed service behavior. |
| Promote 1.1.0 | Both endpoints return 200 and the version is `1.1.0` | Shows a successful subsequent release and records its digest for recovery. |
| Tamper with a copy of 1.2.0 | Promotion is rejected for digest mismatch; state bytes remain unchanged at 1.1.0 | Corruption is tested against the original build digest, not a digest recomputed from the altered ZIP. |
| Run intact 1.2.0 with injected failure | `/health` returns 503; `/version` still identifies `1.2.0` | A valid package can still fail operational acceptance. |
| Restore 1.1.0 | The prior package is reverified and restarted; health is 200/`ok`, version is `1.1.0`, and the restored digest equals the earlier successful release digest | Recovery is observed through HTTP as well as a release-state record. |

The failure is injected by [demo_service.py](demo_service.py) in the candidate worker's handler. The packaged app is unchanged, and no fault switch is added to its runtime interface. This is a deliberate test condition, not a discovered defect in version 1.2.0.

## 3:30–4:15 — Follow recovery and cleanup

The harness records the candidate, starts it, rejects its observed health, then stops that worker before calling `rollback`. It verifies the restored package again before loading its `app.py`, starts a new worker and checks both health and expected version. A healthy response from the wrong version fails the gate.

Each worker listens on a separate operating-system-assigned loopback port. Workers run sequentially and are terminated and waited for, including when an exception occurs. Temporary packages and state are removed when the run ends. Only the requested evidence files remain. You can rerun the command without deleting a release folder first.

## 4:15–5:00 — Explain the boundaries

- **Trust:** expected digests come from local build results in this exercise. Production needs a separately trusted build record; a checksum is not a signature. The `a…`, `b…` and `c…` commit identifiers are explicitly synthetic, not attested Git provenance.
- **State:** the candidate is recorded before health acceptance. This local harness handles the expected failure, but the record is not a production deployment transaction. Concurrent promotion, controller crashes and durable recovery need their own design.
- **Traffic:** restarting workers on different local ports does not prove traffic switching, zero downtime, load-balancer behavior or connection draining.
- **Application behavior:** the demo observes `/health` and `/version`. It does not test a representative business transaction, database compatibility, dependency outages or release rollback in Azure.
- **Failure handling:** a missing or corrupt retained package prevents recovery. Existing tests check that corrupt rollback bytes leave state unchanged; the new startup test verifies that changed bytes cannot launch a worker.

## Evidence and source

Open the [Delivery validation and release workflow](https://github.com/baileynyx/secure-delivery-reference/actions/workflows/delivery.yml), select a run for the commit being reviewed, and inspect the `test` job. It runs the 13 tests, the original record-only rehearsal, this HTTP rehearsal and the Docker build. The separate `codeql` job performs analysis.

The `delivery-failure-evidence-…` artifact contains the generated JSON and Markdown observations and is retained for 14 days. Its successful upload is not a permanent archive. CodeQL completion does not mean there are no alerts or that a severity policy was enforced. The manual release job remains restricted to an explicitly dispatched run on `main`.

[Validation record](VALIDATION.md) · [Project overview](README.md) · [Failure tests](tests/test_failure_demo.py)
