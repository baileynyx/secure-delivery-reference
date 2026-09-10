"""Exercise real GitHub CLI verification against a genuinely signed release.

Run only after the release workflow creates its bundle. Unlike unit tests, this
command has no mocked verifier. State changes are confined to a temporary folder.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import delivery
import provenance


def run_demo(artifact, digest, commit, bundle):
    """Require a valid control before and after deliberately rejected inputs."""
    observations = []
    delivery.verify_release(artifact, digest, commit, bundle)
    observations.append({'case': 'trusted_release', 'result': 'accepted'})
    with tempfile.TemporaryDirectory(prefix='provenance-demo-') as folder:
        root = Path(folder)
        state = root / 'state.json'
        delivery.promote_release(artifact, digest, state, commit, bundle)
        before = state.read_bytes()
        altered = root / 'altered.zip'
        altered.write_bytes(Path(artifact).read_bytes() + b'altered after signing')
        # Recompute the sidecar deliberately: checksum checks alone accept this
        # still-readable ZIP, but the signed subject digest must reject it.
        altered_digest = hashlib.sha256(altered.read_bytes()).hexdigest()
        invalid_bundle = root / 'invalid.jsonl'
        invalid_bundle.write_text('{}\n')
        for name, candidate, expected, proof in (
            ('altered_artifact_and_checksum', altered, altered_digest, bundle),
            ('missing_bundle', artifact, digest, root / 'missing.jsonl'),
            ('invalid_bundle', artifact, digest, invalid_bundle),
        ):
            try:
                delivery.promote_release(candidate, expected, state, commit, proof)
            except provenance.ProvenanceError:
                if state.read_bytes() != before:
                    raise RuntimeError('Rejected promotion changed release state.')
                observations.append({'case': name, 'result': 'rejected', 'state_unchanged': True})
            else:
                raise RuntimeError(f'Unsafe acceptance: {name}')

        # Exercise certificate policy directly with the same valid bundle. These
        # overrides exist only in this demonstration, never in the promotion CLI.
        for name, flag, unexpected in (
            ('unexpected_repository', '--repo', 'baileynyx/unexpected-origin'),
            ('unexpected_workflow', '--cert-identity', provenance.IDENTITY.replace('delivery.yml', 'other.yml')),
            ('unexpected_ref', '--source-ref', 'refs/heads/untrusted'),
            ('unexpected_commit', '--source-digest', ('b' if commit != 'b' * 40 else 'c') * 40),
        ):
            command = provenance.verification_command(artifact, commit, bundle)
            command[command.index(flag) + 1] = unexpected
            result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, timeout=90, check=False)
            if result.returncode != 1:
                raise RuntimeError(f'{name}: expected verification rejection (exit 1), got {result.returncode}')
            observations.append({'case': name, 'result': 'rejected', 'verifier_exit': result.returncode})

    # A broken verifier/connectivity cannot satisfy the complete demonstration.
    delivery.verify_release(artifact, digest, commit, bundle)
    observations.append({'case': 'trusted_release_final_control', 'result': 'accepted'})
    return {'result': 'passed', 'verification': 'real GitHub CLI; no mocks',
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'source_commit': commit, 'sha256': digest, 'observations': observations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run_demo(args.artifact, args.sha256, args.commit, args.bundle)
        delivery.atomic_json(args.output, result)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f'Provenance demonstration failed: {error}\n')


if __name__ == '__main__': main()
