"""Policy and failure atomicity tests; mocked gh is not cryptographic evidence."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import delivery
import provenance
import provenance_demo


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.commit = 'a' * 40
        self.artifact, self.digest = delivery.build(
            Path(__file__).resolve().parents[1], self.root, '1.0.0', self.commit)
        self.state = self.root / 'state.json'
        self.bundle = self.root / 'bundle.jsonl'
        self.bundle.write_text('{"test_fixture_only": true}\n')

    def test_policy_anchors_certificate_source_and_hosted_builder(self):
        command = provenance.verification_command(self.artifact, self.commit, self.bundle)
        required = {
            '--hostname': 'github.com', '--repo': 'baileynyx/secure-delivery-reference',
            '--signer-workflow': 'baileynyx/secure-delivery-reference/.github/workflows/delivery.yml',
            '--cert-identity': 'https://github.com/baileynyx/secure-delivery-reference/.github/workflows/delivery.yml@refs/heads/main',
            '--cert-oidc-issuer': 'https://token.actions.githubusercontent.com',
            '--source-ref': 'refs/heads/main', '--source-digest': self.commit,
            '--signer-digest': self.commit, '--predicate-type': 'https://slsa.dev/provenance/v1',
            '--bundle': str(self.bundle.resolve()),
        }
        for flag, value in required.items():
            self.assertEqual(command[command.index(flag) + 1], value, flag)
        self.assertIn('--deny-self-hosted-runners', command)
        self.assertNotIn('--bundle', provenance.verification_command(self.artifact, self.commit))

    def test_successful_verifier_allows_public_cli_promotion(self):
        with patch('provenance.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                delivery.main(['promote', str(self.artifact), '--sha256', self.digest,
                               '--commit', self.commit, '--bundle', str(self.bundle),
                               '--state', str(self.state)])
        self.assertEqual(json.loads(self.state.read_text())['active']['sha256'], self.digest)
        self.assertEqual(run.call_args.kwargs['timeout'], 90)
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_rejected_verifier_preserves_existing_state(self):
        self.state.write_text('{"active": null, "previous": null}\n')
        before = self.state.read_bytes()
        for code in (1, 2, 127):
            with self.subTest(code=code), patch('provenance.subprocess.run', return_value=subprocess.CompletedProcess([], code)):
                with self.assertRaises(provenance.ProvenanceError):
                    delivery.promote_release(self.artifact, self.digest, self.state, self.commit)
            self.assertEqual(self.state.read_bytes(), before)

    def test_verifier_outages_never_create_state(self):
        for failure in (FileNotFoundError(), subprocess.TimeoutExpired('gh', 90)):
            with self.subTest(failure=failure), patch('provenance.subprocess.run', side_effect=failure):
                with self.assertRaises(provenance.ProvenanceError):
                    delivery.promote_release(self.artifact, self.digest, self.state, self.commit)
            self.assertFalse(self.state.exists())

    def test_missing_or_empty_bundle_does_not_fall_back_to_online(self):
        for path in (self.root / 'missing', self.root / 'empty'):
            if path.name == 'empty': path.touch()
            with patch('provenance.subprocess.run') as run:
                with self.assertRaises(provenance.ProvenanceError):
                    delivery.promote_release(self.artifact, self.digest, self.state, self.commit, path)
                run.assert_not_called()
            self.assertFalse(self.state.exists())

    def test_manifest_cannot_choose_approved_commit(self):
        with patch('provenance.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'approved source commit'):
                delivery.promote_release(self.artifact, self.digest, self.state, 'b' * 40)
            run.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_invalid_commit_rejected_before_verifier(self):
        for commit in ('main', '--help', 'A' * 40, 'a' * 39):
            with self.subTest(commit=commit), self.assertRaises(provenance.ProvenanceError):
                provenance.verification_command(self.artifact, commit)

    def test_altered_bytes_with_recomputed_digest_still_require_attestation(self):
        self.artifact.write_bytes(self.artifact.read_bytes() + b'altered')
        changed = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        with patch('provenance.subprocess.run', return_value=subprocess.CompletedProcess([], 1)) as run:
            with self.assertRaises(provenance.ProvenanceError):
                delivery.promote_release(self.artifact, changed, self.state, self.commit, self.bundle)
            run.assert_called_once()
        self.assertFalse(self.state.exists())

    def test_mutation_during_verification_is_rejected_before_state_write(self):
        def mutate(*args, **kwargs):
            self.artifact.write_bytes(self.artifact.read_bytes() + b'changed')
            return subprocess.CompletedProcess([], 0)
        with patch('provenance.subprocess.run', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                delivery.promote_release(self.artifact, self.digest, self.state, self.commit)
        self.assertFalse(self.state.exists())

    def test_cli_has_no_checksum_only_promotion_or_rollback(self):
        commands = [['promote', str(self.artifact), '--sha256', self.digest], ['rollback']]
        for command in commands:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                delivery.main(command)
            self.assertEqual(error.exception.code, 2)

    def test_rollback_rechecks_previous_provenance_and_preserves_state_on_failure(self):
        delivery.promote(self.artifact, self.digest, self.state)
        newer, digest = delivery.build(Path(__file__).resolve().parents[1], self.root, '1.1.0', 'b' * 40)
        delivery.promote(newer, digest, self.state)
        before = self.state.read_bytes()
        with patch('provenance.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaises(provenance.ProvenanceError):
                delivery.rollback_release(self.state, self.commit, self.bundle)
        self.assertEqual(self.state.read_bytes(), before)
        with patch('provenance.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
            result = delivery.rollback_release(self.state, self.commit, self.bundle)
        self.assertEqual(result['active']['sha256'], self.digest)
        self.assertIn(str(self.artifact.resolve()), run.call_args.args[0])


    def test_evidence_harness_exercises_all_cases_with_simulated_verifier(self):
        def simulated_verifier(command, **kwargs):
            accepted = (command[3] == str(self.artifact.resolve())
                        and command[command.index('--bundle') + 1] == str(self.bundle.resolve())
                        and command[command.index('--repo') + 1] == provenance.REPOSITORY
                        and command[command.index('--cert-identity') + 1] == provenance.IDENTITY
                        and command[command.index('--source-ref') + 1] == provenance.REF
                        and command[command.index('--source-digest') + 1] == self.commit)
            return subprocess.CompletedProcess(command, 0 if accepted else 1)
        with patch('provenance.subprocess.run', side_effect=simulated_verifier):
            evidence = provenance_demo.run_demo(self.artifact, self.digest, self.commit, self.bundle)
        self.assertEqual(evidence['result'], 'passed')
        self.assertEqual(len(evidence['observations']), 9)
        self.assertEqual(sum(x['result'] == 'rejected' for x in evidence['observations']), 7)

    def test_evidence_harness_cannot_pass_with_broken_verifier(self):
        with patch('provenance.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaises(provenance.ProvenanceError):
                provenance_demo.run_demo(self.artifact, self.digest, self.commit, self.bundle)

    def test_evidence_harness_fails_if_altered_bytes_are_accepted(self):
        with patch('provenance.subprocess.run', return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaisesRegex(RuntimeError, 'Unsafe acceptance'):
                provenance_demo.run_demo(self.artifact, self.digest, self.commit, self.bundle)


if __name__ == '__main__': unittest.main()
