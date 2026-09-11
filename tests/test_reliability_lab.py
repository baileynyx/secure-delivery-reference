"""Verify alert decisions independently, then exercise real loopback recovery."""
import contextlib
import io
import math
from pathlib import Path
import tempfile
import unittest

import reliability_lab as lab


class AlertTests(unittest.TestCase):
    def feed(self, monitor, healthy, duration=1.0):
        """Construct observations explicitly; do not reuse the HTTP probe logic."""
        return monitor.observe({'sequence': len(monitor.samples) + 1,
                                'healthy': healthy, 'duration_ms': duration})

    def test_incomplete_window_never_fires(self):
        monitor = lab.Monitor()
        for _ in range(4):
            self.assertIsNone(self.feed(monitor, False))
        self.assertFalse(monitor.active)

    def test_isolated_error_is_not_an_incident(self):
        monitor = lab.Monitor()
        transitions = [self.feed(monitor, state) for state in
                       [True] * 8 + [False] + [True] * 8]
        self.assertTrue(all(item is None for item in transitions))

    def test_sustained_errors_fire_once_at_expected_boundary(self):
        monitor = lab.Monitor()
        for _ in range(5):
            self.feed(monitor, True)
        for _ in range(3):
            self.assertIsNone(self.feed(monitor, False))
        event = self.feed(monitor, False)
        self.assertEqual(event['event'], 'alert_fired')
        self.assertEqual(event['sample_sequence'], 9)
        self.assertEqual(event['window']['errors'], 4)
        for _ in range(6):
            self.assertIsNone(self.feed(monitor, False))

    def test_successful_but_slow_responses_can_alert(self):
        monitor = lab.Monitor()
        for _ in range(5):
            self.feed(monitor, True)
        self.assertIsNone(self.feed(monitor, True, 700.0))
        self.assertEqual(self.feed(monitor, True, 700.0)['event'], 'alert_fired')

    def test_clear_needs_two_complete_healthy_windows(self):
        monitor = lab.Monitor()
        for _ in range(6):
            self.feed(monitor, False)
        self.assertTrue(monitor.active)
        for _ in range(5):
            self.assertIsNone(self.feed(monitor, True))
        self.assertEqual(self.feed(monitor, True)['event'], 'alert_cleared')
        self.assertFalse(monitor.active)

    def test_nearest_rank_p95_and_invalid_latency(self):
        samples = [{'healthy': i != 20, 'duration_ms': float(i)} for i in range(1, 21)]
        self.assertEqual(lab.summarize(samples),
                         {'requests': 20, 'errors': 1, 'error_ratio': 0.05, 'p95_ms': 19.0})
        for value in (-1, math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                lab.summarize([{'healthy': True, 'duration_ms': value}])


class RehearsalTests(unittest.TestCase):
    def test_real_http_incident_and_recovery(self):
        # No mock HTTP responses or clocks: the owned workers actually return
        # 200/503, the package is rolled back, and its version is rechecked.
        report, samples = lab.run_lab(interval=0)
        self.assertEqual(report['result'], 'passed')
        self.assertEqual(report['phases']['baseline']['requests'], 12)
        self.assertEqual(report['phases']['baseline']['errors'], 0)
        self.assertEqual(report['phases']['incident']['requests'], 4)
        self.assertEqual(report['phases']['incident']['errors'], 4)
        self.assertEqual(report['phases']['recovery']['requests'], 12)
        self.assertEqual(report['phases']['recovery']['errors'], 0)
        self.assertEqual([s['status'] for s in samples], [200] * 12 + [503] * 4 + [200] * 12)
        names = [item['event'] for item in report['timeline']]
        self.assertEqual(names, ['baseline_started', 'baseline_verified', 'fault_observed',
                                'alert_fired', 'recovery_started', 'restored_service_ready',
                                'alert_cleared', 'recovery_verified', 'cleanup_complete'])
        self.assertEqual(report['restored_release']['version'], '1.0.0')
        self.assertNotEqual(report['restored_release']['sha256'], report['candidate_release']['sha256'])
        self.assertTrue(all(value >= 0 for value in report['measurements'].values()))
        export = lab.metrics_text(report, samples)
        self.assertIn('lab_http_requests_total{phase="incident",outcome="failure"} 4', export)
        self.assertIn('| recovery | 12 | 0 | 0%', lab.markdown(report))

    def test_existing_evidence_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            sentinel = Path(temp) / 'keep.txt'
            sentinel.write_text('earlier evidence', encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(lab.main(['--output-dir', temp]), 2)
            self.assertEqual(sentinel.read_text(), 'earlier evidence')
            self.assertEqual(list(Path(temp).iterdir()), [sentinel])


if __name__ == '__main__':
    unittest.main()
