"""Verify observed recovery and worker cleanup through the real local harness."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import delivery
import failure_demo


ROOT = Path(__file__).resolve().parents[1]


class FailureDemoTests(unittest.TestCase):
    def test_cli_observes_failed_candidate_and_recovers_prior_digest(self):
        """The public command must prove HTTP recovery, not just change a record."""
        with tempfile.TemporaryDirectory() as output:
            result = subprocess.run(
                [sys.executable, str(ROOT / 'failure_demo.py'), '--output-dir', output],
                cwd=ROOT, capture_output=True, text=True, timeout=60, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((Path(output) / 'evidence.json').read_text(encoding='utf-8'))
            self.assertEqual(json.loads(result.stdout), report)
            self.assertEqual(report['result'], 'passed')
            healthy, upgraded, tampered, recovery = report['scenarios']
            self.assertEqual(healthy['observed']['version']['body']['version'], '1.0.0')
            self.assertEqual(upgraded['observed']['version']['body']['version'], '1.1.0')
            self.assertTrue(tampered['state_unchanged'])
            self.assertEqual(tampered['promotion'], 'rejected')
            self.assertEqual(recovery['candidate_observed']['health']['status'], 503)
            self.assertEqual(recovery['restored_sha256'], upgraded['sha256'])
            self.assertNotEqual(recovery['restored_sha256'], healthy['sha256'])
            self.assertEqual(recovery['restored_observed'], {
                'health': {'status': 200, 'body': {'status': 'ok'}},
                'version': {'status': 200, 'body': {'version': '1.1.0'}},
            })
            self.assertIn(upgraded['sha256'], (Path(output) / 'evidence.md').read_text(encoding='utf-8'))

    def test_wrong_version_fails_gate_and_exception_stops_worker(self):
        """A healthy wrong version must fail; exceptional exit must close its port."""
        with tempfile.TemporaryDirectory() as temp:
            artifact, digest = delivery.build(ROOT, Path(temp), '1.0.0', 'a' * 40)
            record = delivery.verify(artifact, digest)
            with self.assertRaisesRegex(RuntimeError, 'unexpected version'):
                with failure_demo.running_release(record) as url:
                    observed = failure_demo.observe_service(url)
                    failure_demo.require_healthy(observed, '9.9.9')
            # The context manager has waited for process exit, not merely sent a
            # termination signal. A new connection should no longer be accepted.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with self.assertRaises(urllib.error.URLError):
                opener.open(url + '/health', timeout=1)

    def test_corrupted_retained_package_cannot_start_a_worker(self):
        """Startup must reverify the package even when its state record is valid."""
        with tempfile.TemporaryDirectory() as temp:
            artifact, digest = delivery.build(ROOT, Path(temp), '1.0.0', 'a' * 40)
            record = delivery.verify(artifact, digest)
            artifact.write_bytes(artifact.read_bytes() + b'corruption-after-verification')
            with patch('failure_demo.subprocess.Popen') as launch:
                with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                    with failure_demo.running_release(record):
                        self.fail('A corrupt release reached startup.')
                launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
