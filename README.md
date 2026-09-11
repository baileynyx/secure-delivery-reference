# Secure delivery reference

A deliberately small Python service with a delivery workflow you can inspect: HTTP tests, deterministic release ZIPs, GitHub build attestations, provenance-gated local promotion and an HTTP failure-and-recovery rehearsal.

**Scope:** local demonstration and GitHub CI configuration. The promotion command records release state; a separate demo harness starts disposable loopback workers to verify recovery. No Azure target is configured.

**Build trust:** [Follow the provenance walkthrough](PROVENANCE.md) for the fixed repository/workflow policy, signed release verification and rejection evidence. Unit tests simulate the verifier. CI additionally verifies a historical signed release using the real GitHub CLI; new signatures are generated only by a manual release on `main`.

**Engineering case study:** [When green tests missed a release verification failure](docs/attestation-verification-case-study.md) traces the CLI incompatibility, the preserved trust policy and the real-signature regression check.

**Verified fresh release:** [Version 1.0.1 completed build, signing, verification and evidence upload](https://github.com/baileynyx/secure-delivery-reference/actions/runs/34453548353), with two accepted controls and seven rejected cases. [Read the validation record](VALIDATION.md#fresh-signed-release-version-101) for the exact commit, package digest and scope.

## Start here: failure and recovery demo

[Follow the five-minute walkthrough](DEMO.md) to see a successful release, tampered-package rejection, an injected HTTP 503 failure and verified recovery to the previous package.

```shell
# From this repository's root, run the disposable HTTP rehearsal and retain
# JSON/Markdown observations after its temporary packages and workers are removed.
python failure_demo.py --output-dir reports/failure-demo
```

Requires Python 3.11 or later plus local child-process and loopback access. The expected result is `passed`: 1.0.0 and 1.1.0 serve healthy responses, altered 1.2.0 bytes are rejected without a state change, and an intact 1.2.0 with injected unhealthy behavior is replaced by verified 1.1.0. The [walkthrough](DEMO.md) explains expected outputs, evidence and limits.

## Measure detection and recovery

The [service reliability lab](docs/reliability-lab.md) adds synthetic traffic,
request latency, sustained-error alerting and a documented recovery runbook to the
existing disposable HTTP service. Run it from the repository root with Python 3.12+:

```shell
# A new report directory is chosen automatically, preserving earlier evidence.
python reliability_lab.py
```

It records the baseline, injected HTTP 503s, alert, rollback and verified recovery.
Results include raw samples, an incident report and a Prometheus-text snapshot.
The short sample windows and local timings describe a rehearsal, not production
SLO compliance. [Inspect the retained local capture](docs/evidence/reliability-local/README.md).

## Run locally

Requires Python 3.11 or later and no Python packages.

```shell
python -m unittest discover -s tests -v
python rehearse.py
python app.py
```

Open `http://127.0.0.1:8080/health` and `/version`. Stop with Ctrl+C. The rehearsal prints a simulated promotion from 1.0.0 to 1.1.0 and verified restoration of 1.0.0, then removes its temporary files.

Optional container:

```shell
docker build -t delivery-demo .
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges -p 127.0.0.1:8080:8080 delivery-demo
```

The image runs as numeric UID 10001. Python's standard HTTP server is suitable for this demonstration, not a production internet service.

## Build and inspect a local source package

From a committed Git checkout, in PowerShell:

```powershell
$commit = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'A Git commit is required.' }
$result = python delivery.py build --version 1.0.0 --commit $commit | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
python delivery.py verify $result.artifact --sha256 $result.sha256
```

This checks integrity and package structure only. Local builds do not have a trusted GitHub attestation and cannot pass the release promotion CLI. Use [PROVENANCE.md](PROVENANCE.md) to download and verify a signed workflow release, promote it with an explicitly approved commit, and reverify provenance during rollback.

The expected digest and approved commit must come from the reviewed build record. A checksum alone does not establish authenticity. Local builds can include uncommitted changes; the CI release job checks out its exact commit, builds the package and signs provenance for those bytes. Promotion and rollback only update `runtime/state.json`; a deployment adapter must separately switch the running service and check health.

## Workflow and trust boundaries

| Stage | Behavior |
| --- | --- |
| Pull request | Read-only checkout, unit/HTTP tests, failure-and-recovery evidence, Docker build, CodeQL analysis |
| Release request | Manual workflow on main; tests and CodeQL must succeed before packaging |
| Package | Fixed ZIP metadata, explicit source commit, SHA-256 sidecar and signed Sigstore bundle; upload retained 14 days |
| Promotion | Verify bytes, manifest and attestation against the fixed repository/workflow/main policy and approved commit before updating local state |
| Recovery | Require the previous release's approved commit and valid provenance; the separate unsigned local harness exercises HTTP recovery |

Workflow actions are pinned to upstream commit SHAs, with Dependabot updates. Token permissions are read-only except CodeQL's security-event upload and the manual release job's OIDC/attestation writes. PR jobs cannot mint release attestations through this workflow. No cloud credentials or `pull_request_target` trigger are used. CodeQL completion is not a guarantee of zero alerts: **the included workflow does not query alert severity to block a release**. Set repository code-scanning rules for your severity policy before treating it as a production security gate.

## Recovery exercise for a real environment

Retain the prior immutable package and its trusted digest. After a failed rollout, stop promotion, switch the deployment target to the prior verified artifact, and check both `/health` and `/version` plus a representative transaction. Record expected and observed versions, digest, health, operator and timestamps. Database migrations require a separate compatibility and recovery plan.

The original `rehearse.py` exercises release-state recovery only. The new `failure_demo.py` additionally executes locally built packages in disposable processes and observes HTTP health/version after recovery. It uses different loopback ports, injects the health failure in a harness, and does not test production traffic switching, database recovery or a cloud deployment adapter. See [DEMO.md](DEMO.md).

## Production extensions

Use a production HTTP server, a digest-pinned and scanned container base, workload identity federation, protected deployment environments, durable artifact retention with attestations, severity-based scanning rules, authenticated health checks, and a deployment adapter with health-gated rollout. Add locking or transactional storage before multiple operators can promote concurrently. Current state is local and unauthenticated.

See `VALIDATION.md` for executed checks. [GitHub's secure workflow guidance](https://docs.github.com/en/actions/reference/security/secure-use) explains action pinning and token boundaries; [code scanning configuration](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options) documents the scan setup.
