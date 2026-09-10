# Validation

## Provenance gate increment

Local Python validation passed **27 tests**: the previous 13 plus 14 provenance
policy, CLI, rejection atomicity, rollback and evidence-harness tests. These tests
mock GitHub CLI responses; they validate the integration contract and fail-closed
behavior, not real signature cryptography. They include unavailable/timed-out
verification, missing proof, wrong approved commit, changed bytes with a recomputed
digest, mutation during verification and refusal to accept unsafe evidence.

The manual `main` release job is configured to generate a real GitHub attestation,
run the live positive/rejection exercise and upload its evidence with the bundle.
**That signed release has not been executed for this increment.** A passing PR
run cannot establish successful signing. Follow [PROVENANCE.md](PROVENANCE.md)
after merge and record the exact successful release-run URL and source commit.

GitHub CLI, Docker and CodeQL are not available in the local validation environment.
Inspect the hosted PR results for Docker/CodeQL evidence. No deployment occurred.

## Loopback failure and recovery increment

Local Python validation passed all **13 tests**: the original 10 plus three tests for the public HTTP rehearsal/report command, wrong-version rejection with worker cleanup on exception, and refusal to launch a corrupted retained package.

`python failure_demo.py --output-dir reports/failure-demo` also completed successfully. It observed healthy 1.0.0 and 1.1.0 responses, rejected a tampered copy of 1.2.0 without changing state, observed the harness-injected HTTP 503 from intact 1.2.0, and reverified/restarted 1.1.0 with HTTP 200 health and the expected version and digest. Generated evidence includes UTC execution timestamps; temporary workers, packages and state are removed.

The workflow now runs this rehearsal and uploads JSON/Markdown evidence retained for 14 days. Check the hosted result for the exact PR commit; these local results do not claim Docker or CodeQL execution. No Azure deployment, production traffic switch, database rollback or concurrent-operator recovery was performed.

## Original baseline

September 9, 2026: `python -m unittest discover -s tests -v` passed all **10 tests**, covering an actual loopback HTTP health request, version/unknown-route responses, reproducible ZIP bytes, overwrite refusal, invalid release metadata, tamper rejection, rollback, repeated promotion and unavailable/corrupted previous releases.

`python rehearse.py` completed a local release-state simulation: version 1.0.0 was recorded, 1.1.0 was promoted, and rollback restored the original 1.0.0 digest. Synthetic commit identifiers are explicitly confined to the rehearsal and tests.

The [first hosted delivery workflow](https://github.com/baileynyx/secure-delivery-reference/actions/runs/34357996018) passed for source commit `684aaf553a29f193202cf894cf491732455802b8`: tests, the local rehearsal, Docker image build and CodeQL initialization/analysis all completed successfully. Successful analysis does not establish that no security alerts exist.

The manual release job was correctly skipped on this historical push. Container runtime checks, manual release packaging on GitHub and live deployment were not executed. At that baseline, the rehearsal updated release records only; the loopback HTTP increment described above is separate from a production deployment target.
