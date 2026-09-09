# Secure delivery reference

A deliberately small Python service with a delivery workflow you can inspect: HTTP tests, deterministic release ZIPs, source-commit metadata, checksum verification, local promotion records and a rollback rehearsal.

**Scope:** local demonstration and GitHub CI configuration. The promotion command records release state; it does not deploy or restart a running service. No Azure target is configured.

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

## Build and verify a real source release

From a committed Git checkout, in PowerShell:

```powershell
$commit = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'A Git commit is required.' }
$result = python delivery.py build --version 1.0.0 --commit $commit | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
python delivery.py verify $result.artifact --sha256 $result.sha256
python delivery.py promote $result.artifact --sha256 $result.sha256
```

Build another version and promote it to establish a previous release, then use `python delivery.py rollback`. Promotion and rollback only update `runtime/state.json`; a real deployment adapter must consume the verified package, switch the running service, check health and application behavior, then record success.

The trusted expected digest must come from the approved build record. A hash obtained from the same untrusted location as an artifact does not establish authenticity. Source metadata is recorded, not cryptographically attested. Local manual builds can include uncommitted changes; the CI release job uses a clean checkout and records its exact commit.

## Workflow and trust boundaries

| Stage | Behavior |
| --- | --- |
| Pull request | Read-only checkout, unit/HTTP tests, Docker build, CodeQL analysis |
| Release request | Manual workflow on main; tests and CodeQL must succeed before packaging |
| Package | Fixed ZIP metadata, explicit source commit, SHA-256 sidecar; upload retained 14 days |
| Promotion | Verify bytes and manifest before atomically updating a local single-operator state file |
| Recovery | Reverify the previous retained artifact before restoring its release record |

Workflow actions are pinned to upstream commit SHAs, with Dependabot updates. Token permissions are read-only except the CodeQL job's security-event upload. No cloud credentials or `pull_request_target` trigger are used. CodeQL completion is not a guarantee of zero alerts: **the included workflow does not query alert severity to block a release**. Set repository code-scanning rules for your severity policy before treating it as a production security gate.

## Recovery exercise for a real environment

Retain the prior immutable package and its trusted digest. After a failed rollout, stop promotion, switch the deployment target to the prior verified artifact, and check both `/health` and `/version` plus a representative transaction. Record expected and observed versions, digest, health, operator and timestamps. Database migrations require a separate compatibility and recovery plan.

The included `rehearse.py` exercises release-state recovery only. HTTP behavior is tested separately; it does not claim end-to-end deployment recovery.

## Production extensions

Use a production HTTP server, a digest-pinned and scanned container base, workload identity federation, protected deployment environments, durable artifact retention with attestations, severity-based scanning rules, authenticated health checks, and a deployment adapter with health-gated rollout. Add locking or transactional storage before multiple operators can promote concurrently. Current state is local and unauthenticated.

See `VALIDATION.md` for executed checks. [GitHub's secure workflow guidance](https://docs.github.com/en/actions/reference/security/secure-use) explains action pinning and token boundaries; [code scanning configuration](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options) documents the scan setup.
