# When green tests missed a release verification failure

**Engineering case study · GitHub Actions · Build provenance · Failure diagnosis**

A manual release built and signed its package successfully, then stopped at the provenance gate. The integration passed mocked tests but generated a command that the real GitHub CLI would not accept. The correction preserved the exact build-origin policy and added a repeatable check against a genuine signed artifact.

This is an independent portfolio demonstration. It affected a reference release workflow; it was not a customer outage or a production deployment.

## The release contract

The delivery CLI checks package integrity and requires a GitHub attestation before updating local promotion or rollback state. Its policy binds the package to this repository, the delivery workflow on `main`, an independently approved source and signer commit, the expected OIDC issuer, SLSA provenance and a GitHub-hosted runner.

The service and state model are deliberately small. That makes the trust decisions, failure behavior and evidence inspectable without a cloud account.

## What happened

| Evidence | Observation |
| --- | --- |
| [Original implementation, PR #7](https://github.com/baileynyx/secure-delivery-reference/pull/7) | Packaging, state protection and mocked verifier tests passed. |
| [Manual run 34428439084](https://github.com/baileynyx/secure-delivery-reference/actions/runs/34428439084) | Version 1.0.0 was packaged and its attestation published. The following verification step failed, so the release-artifact upload was never reached. |
| [Correction, PR #8](https://github.com/baileynyx/secure-delivery-reference/pull/8) | Removed the incompatible flag combination, exposed bounded diagnostics and added real-verifier integration coverage. |
| [Fix validation, run 34428858194](https://github.com/baileynyx/secure-delivery-reference/actions/runs/34428858194) | All 29 tests, real-signature integration, HTTP recovery rehearsal, Docker build and CodeQL analysis passed. |

The failure was contained: the gate did not accept an unverified package. Signing had already succeeded, leaving a genuine attestation available for diagnosis and regression coverage.

## Root cause and the testing gap

The wrapper supplied both `--signer-workflow` and `--cert-identity`. In [GitHub CLI v2.98.0](https://github.com/cli/cli/blob/v2.98.0/pkg/cmd/attestation/verify/verify.go), those selectors belong to a mutually exclusive flag group. The CLI rejected the invocation before verifying the signature.

The unit tests asserted the intended policy arguments and simulated subprocess success or failure. They proved how the Python wrapper reacted to those outcomes, but never asked the real CLI whether that argument combination was valid. In fact, an assertion required the incompatible combination.

A second problem slowed diagnosis: the wrapper replaced the CLI's explanation with a generic verification error. The visible failure could have suggested a signature, identity, connectivity or CLI compatibility problem.

## Corrective decisions

**Keep the exact identity.** The certificate identity already contains the repository, workflow path and `refs/heads/main`. Removing the redundant workflow selector fixes the invocation while retaining that exact identity requirement. Source/signer commit, repository, issuer, runner and predicate restrictions remain enforced. See [the corrected policy](../provenance.py).

**Make rejection diagnosable.** Failed verification now includes the exit code and bounded CLI diagnostics. Configured authentication tokens are redacted and control characters are flattened. Errors still prevent state changes; diagnostics are not written into release records.

**Exercise the dependency that failed.** [check_provenance.py](../check_provenance.py) reconstructs the historical package from a frozen source fixture and requires its independently recorded SHA-256:

`8700ea411ffee5c1054b8a7d6a00e8969f768be0eb32f8a91d4a2aa124ff74a9`

The fixture represents commit `c934bcc1f10c5e88034539e788e09842ff84e5c4`, version 1.0.0. The check downloads its existing public attestation and invokes the real verifier. It does not execute the fixture, sign PR code or grant signing permissions to the test job.

The fixture's [source and provenance record](../tests/fixtures/signed-release/README.md) explain how to reproduce it.

## What the new integration check demonstrates

The successful run recorded nine observations:

- The genuine signed package passes an initial verification control.
- Altered package bytes with a recomputed checksum, a missing bundle and an invalid bundle are rejected; attempted promotions preserve state.
- Mismatched repository, workflow identity, ref and source-commit expectations are rejected against the valid bundle.
- The genuine package passes a final verification control.

The origin cases change verifier expectations; they do not manufacture certificates from another repository. The two successful controls keep an always-failing verifier from satisfying the exercise. Rejection exit codes are evidence of refusal, not an independent classification of every cryptographic failure.

The run uploaded `provenance-integration-evidence-34428858194-1`. Workflow artifacts have 14-day retention, so the frozen fixture and runnable check support reproduction after that report expires.

## Outcome and remaining boundary

The corrected wrapper passed the historical real-signature regression check, then completed a fresh version **1.0.1** release in [manual run 34453548353](https://github.com/baileynyx/secure-delivery-reference/actions/runs/34453548353) on September 10, 2026. The same run built the package from commit `556a4057d71be166bdc0339737140277db0610a2`, created its attestation, accepted two trusted controls, rejected seven negative cases and uploaded the package, checksum, original bundle and evidence.

All 29 tests, HTTP recovery, Docker build and CodeQL analysis passed in that run. The [validation record](../VALIDATION.md#fresh-signed-release-version-101) identifies the package digest, artifact and retained observations. This closes the fresh-release gap that was pending when the case study was first written.

This reference also does not prove cloud deployment, production traffic switching, concurrent state safety or absence of security vulnerabilities. CodeQL completed; no severity-based release blocking policy is claimed.

The engineering lesson is specific: mocks established the wrapper's behavior, but omitted the external CLI's invocation contract. A small, repeatable real-verifier check now covers that boundary while keeping the fast unit tests.

[Project overview](../README.md) · [Verification walkthrough](../PROVENANCE.md) · [Validation history](../VALIDATION.md)
