"""Delegate signature verification to GitHub CLI under a fixed release policy.

This module does not parse an unsigned JSON claim as proof. GitHub CLI verifies
the Sigstore bundle, artifact digest and certificate identity. Keep policy in
reviewed source; never take repository/workflow identities from the package.
"""
from pathlib import Path
import os
import re
import subprocess

REPOSITORY = 'baileynyx/secure-delivery-reference'
WORKFLOW = f'{REPOSITORY}/.github/workflows/delivery.yml'
REF = 'refs/heads/main'
IDENTITY = f'https://github.com/{WORKFLOW}@{REF}'


class ProvenanceError(ValueError):
    """Verification was rejected or could not be completed; do not promote."""


def verification_command(artifact, commit, bundle=None):
    """Pin source and signer identities to the operator's approved commit.

    The workflow is not reusable, so its signer digest is the source commit.
    An absolute artifact path also prevents a filename becoming a CLI option.
    """
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ProvenanceError('Approved commit must be 40 lowercase hexadecimal characters.')
    command = [
        'gh', 'attestation', 'verify', str(Path(artifact).resolve()),
        '--hostname', 'github.com', '--repo', REPOSITORY,
        # GitHub CLI makes signer-workflow and cert-identity mutually exclusive.
        # The exact SAN already binds repository, workflow path AND main ref.
        '--cert-identity', IDENTITY,
        '--cert-oidc-issuer', 'https://token.actions.githubusercontent.com',
        '--source-ref', REF, '--source-digest', commit,
        '--signer-digest', commit, '--deny-self-hosted-runners',
        '--predicate-type', 'https://slsa.dev/provenance/v1',
    ]
    if bundle is not None:
        bundle = Path(bundle).resolve()
        if not bundle.is_file() or bundle.stat().st_size == 0:
            raise ProvenanceError('Attestation bundle is missing or empty.')
        command.extend(['--bundle', str(bundle)])
    return command


def diagnostic(result):
    """Keep bounded CLI diagnostics while redacting configured auth tokens."""
    message = result.stderr or result.stdout or 'No verifier diagnostic was returned.'
    for name in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'):
        secret = os.environ.get(name)
        if secret:
            message = message.replace(secret, '[REDACTED]')
    # Flatten control characters/newlines so subprocess text cannot introduce
    # new GitHub workflow-command lines or terminal escape sequences in logs.
    message = ' '.join(''.join(c if c.isprintable() else ' ' for c in message).split())
    return message[-2000:]


def verify(artifact, commit, bundle=None):
    """Fail closed on rejected signatures, unavailable CLI, or network errors."""
    command = verification_command(artifact, commit, bundle)
    try:
        # No shell, interactive prompts or indefinite wait. Failed verification
        # reports bounded diagnostics without adding them to release-state records.
        result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=90,
                                check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProvenanceError('GitHub attestation verifier unavailable or timed out.') from error
    if result.returncode != 0:
        raise ProvenanceError(
            f'GitHub attestation verification failed (exit {result.returncode}): {diagnostic(result)}')
