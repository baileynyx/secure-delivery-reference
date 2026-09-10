"""Read-only integration check against the first real signed main build.

This uses a frozen source fixture, the independently recorded release digest and
the existing public attestation. It never signs PR code or executes the fixture.
GitHub CLI and Sigstore network access are required; failure is not skipped.
"""
from pathlib import Path
import subprocess
import tempfile

import delivery
import provenance
import provenance_demo

COMMIT = 'c934bcc1f10c5e88034539e788e09842ff84e5c4'
DIGEST = '8700ea411ffee5c1054b8a7d6a00e8969f768be0eb32f8a91d4a2aa124ff74a9'


def main():
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='signed-fixture-') as folder:
        temporary = Path(folder)
        # Deterministic packaging reproduces the signed subject byte for byte.
        # This is a historical fixture, not an attestation for the current PR.
        artifact, digest = delivery.build(root / 'tests/fixtures/signed-release',
                                          temporary, '1.0.0', COMMIT)
        if digest != DIGEST:
            raise RuntimeError('Historical fixture does not reproduce the approved signed digest.')
        result = subprocess.run(
            ['gh', 'attestation', 'download', str(artifact), '--repo', provenance.REPOSITORY,
             '--hostname', 'github.com'], cwd=temporary, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=90, check=False)
        if result.returncode != 0:
            raise RuntimeError(f'Attestation download failed: {provenance.diagnostic(result)}')
        bundles = list(temporary.glob('*.jsonl'))
        if len(bundles) != 1:
            raise RuntimeError('Expected one downloaded attestation bundle file.')
        evidence = provenance_demo.run_demo(artifact, digest, COMMIT, bundles[0])
        evidence['fixture_run'] = 'https://github.com/baileynyx/secure-delivery-reference/actions/runs/34428439084'
        output = root / 'reports/provenance-integration/evidence.json'
        delivery.atomic_json(output, evidence)
        print(f'Real signed-fixture verification passed: {len(evidence["observations"])} observations; {output}')


if __name__ == '__main__': main()
