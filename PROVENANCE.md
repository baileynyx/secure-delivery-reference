# Verify where a release came from

This reference adds a cryptographic build-origin gate to the existing integrity
and recovery exercises. A checksum says the bytes match an expected digest. A
GitHub attestation additionally binds those bytes to a workflow identity.

**Evidence status:** ordinary tests use a mocked verifier. A real signature check
requires the merged workflow to run manually on `main`; a green PR alone does not
establish that signing or live verification succeeded. No cloud deployment occurs.

## Fixed acceptance policy

The release CLI delegates signature, certificate and subject-digest verification
to [GitHub CLI](https://cli.github.com/manual/gh_attestation_verify). The policy in
[provenance.py](provenance.py) requires all of these constraints:

| Claim | Required value |
| --- | --- |
| Source repository | `baileynyx/secure-delivery-reference` |
| Signer workflow | This repository's `.github/workflows/delivery.yml` |
| Certificate identity | Exact workflow URL ending in `@refs/heads/main` |
| OIDC issuer | `https://token.actions.githubusercontent.com` |
| Source ref | `refs/heads/main` |
| Source and signer commit | Explicit `--commit` approved independently by the operator |
| Runner | GitHub-hosted; self-hosted attestations rejected |
| Predicate | SLSA provenance v1 |
| Package | SHA-256 and allowlisted ZIP/manifest checks also pass |

The approved commit is not inferred from the downloaded manifest. Repository and
workflow identities are not caller-selectable CLI flags. Missing proofs, verifier
errors, timeouts and unsupported CLI flags all prevent promotion. There is no
checksum-only fallback in the public `promote` or `rollback` command.

## Create the first signed release

1. Merge the reviewed implementation and inspect successful `test` and `codeql`
   jobs for the resulting `main` commit.
2. Open [Delivery validation and release](https://github.com/baileynyx/secure-delivery-reference/actions/workflows/delivery.yml),
   select **Run workflow**, choose `main`, and enter a numeric version such as
   `1.0.0`. Confirm the run's exact source commit against the intended revision.
3. Inspect the `release` job. It builds one ZIP, uses the SHA-pinned
   [GitHub attestation action](https://github.com/actions/attest) to sign that ZIP,
   and runs `provenance_demo.py` with the real GitHub CLI and generated bundle.
4. Download the `service-<commit>-<run>-<attempt>` workflow artifact. It contains
   the original service ZIP, SHA-256 sidecar, `provenance.jsonl` and the generated
   `provenance-evidence.json`. Retention is 14 days; archive approved releases
   separately if longer rollback availability is required.

Only the manual `main` release job receives OIDC and attestation write permissions.
PR tests run without signing credentials. Generation follows
[GitHub's artifact attestation guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).

## Verify and promote a downloaded release

Use Python 3.11+ and a current authenticated `gh` installation that supports the
flags in `provenance.py`. Keep the reviewed repository checkout, executable PATH
and local state trusted. Extract the outer workflow-artifact download into
`downloaded/`, leaving the inner `service-*.zip` intact.

From the repository root in PowerShell:

```powershell
# Obtain this SHA from the approved workflow run, never from the package manifest.
$approvedCommit = Read-Host 'Approved full source commit'
$packages = @(Get-ChildItem downloaded -Filter 'service-*.zip' -File)
if ($packages.Count -ne 1) { throw 'Expected exactly one inner service ZIP.' }
$artifact = $packages[0].FullName
$digest = (Get-Content "$artifact.sha256" -Raw).Trim()
$bundle = Join-Path $packages[0].DirectoryName 'provenance.jsonl'

python delivery.py verify-release $artifact --sha256 $digest --commit $approvedCommit --bundle $bundle
if ($LASTEXITCODE -ne 0) { throw 'Release verification failed.' }
python delivery.py promote $artifact --sha256 $digest --commit $approvedCommit --bundle $bundle
if ($LASTEXITCODE -ne 0) { throw 'Promotion refused.' }
```

Compare the sidecar digest to the approved build record. Even a replaced artifact
and recomputed sidecar must fail signature verification against the signed bundle.
Omit `--bundle` to retrieve attestations from GitHub by artifact digest; a supplied
missing/empty bundle fails locally instead of falling back to online lookup.
A local bundle does not by itself guarantee completely offline verification;
authentication and trusted-root/network availability depend on the CLI setup.

After promoting a second approved release, retain the first package and bundle
at their original paths. Rollback requires the **previous** release's approved
commit and bundle:

```powershell
$previousCommit = Read-Host 'Approved full commit of the previous release'
$previousBundle = Read-Host 'Path to the previous release provenance.jsonl'
python delivery.py rollback --commit $previousCommit --bundle $previousBundle
if ($LASTEXITCODE -ne 0) { throw 'Rollback verification failed.' }
```

These commands update local release records only. They do not start a service.

## Explain the rejection evidence

`provenance_demo.py` first accepts the genuine signed release and records a
promotion in disposable state. It then requires rejection of an altered ZIP
**with a recomputed checksum**, a missing bundle, and an invalid bundle; each
failed promotion must leave state bytes unchanged. It separately asks the real
verifier to reject mismatched repository, workflow identity, ref and commit
policies against the valid bundle. A final successful control prevents an
always-failing verifier from producing a passing demonstration.

These origin tests change verifier expectations; they do not forge certificates
or create releases in another repository. Failure exit codes show rejection, not
an independently classified cryptographic cause. Review the run and controls
alongside the report. Evidence is emitted only when every case completes; check
the command exit status and report timestamp before reusing an existing report.

To repeat the live exercise with the PowerShell variables above:

```powershell
python provenance_demo.py $artifact --sha256 $digest --commit $approvedCommit --bundle $bundle --output reports/provenance-evidence.json
if ($LASTEXITCODE -ne 0) { throw 'Provenance exercise failed.' }
```

## Boundaries worth discussing in an interview

The original [HTTP recovery demo](DEMO.md) uses synthetic commits and checksum-only
Python state primitives, explicitly separate from the release CLI. Its fixtures
are not signed release evidence. The unit tests also mock `gh`; only the manual
release exercises real signatures.

This design trusts GitHub/Sigstore roots, the approved workflow and commit, and
the local operator. It does not defend against an operator changing the gate or
state, a compromised trusted builder, concurrent state writers, or a malicious
process racing local files. Attestation proves origin under that trust model,
not absence of vulnerabilities or correct application behavior. Branch review
rules, production deployment approvals and durable artifact storage are separate
controls; this reference does not claim they are configured.
