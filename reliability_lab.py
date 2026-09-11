"""Measure detection and recovery in an isolated, synthetic HTTP incident.

Only packages built from this trusted checkout are executed. Existing delivery
helpers verify bytes and restore local release state; disposable worker processes
bind to loopback on OS-assigned ports. The harness injects HTTP 503 responses into
the candidate. No cloud account, model, external service or third-party package
is needed, and this exercise does not perform signed release promotion.
"""
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

import delivery
from failure_demo import observe_service, require_healthy, running_release

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class AlertPolicy:
    """Short windows make this a quick lab, not a production alert policy.

    Evaluate the last five requests, including unsuccessful requests in latency
    statistics. Two consecutive breached windows fire one alert. Clearing needs
    two full windows with no failed requests and latency below the threshold.
    """
    window: int = 5
    error_ratio: float = 0.6
    p95_ms: float = 500.0
    fire_windows: int = 2
    clear_windows: int = 2


def summarize(samples):
    """Use nearest-rank p95 and include every attempted measured health request."""
    if not samples:
        return {'requests': 0, 'errors': 0, 'error_ratio': 0.0, 'p95_ms': None}
    latencies = sorted(sample['duration_ms'] for sample in samples)
    if any(not math.isfinite(value) or value < 0 for value in latencies):
        raise ValueError('Sample latency must be finite and nonnegative.')
    errors = sum(not sample['healthy'] for sample in samples)
    return {'requests': len(samples), 'errors': errors,
            'error_ratio': errors / len(samples),
            'p95_ms': latencies[math.ceil(0.95 * len(latencies)) - 1]}


class Monitor:
    """Keep alert state separate from release actions and avoid repeat pages."""
    def __init__(self, policy=None):
        self.policy = policy or AlertPolicy()
        self.samples = []
        self.active = False
        self.breaches = 0
        self.clears = 0

    def observe(self, sample):
        # Validate before accepting a sample so NaN cannot bypass a comparison.
        summarize([sample])
        self.samples.append(sample)
        window = self.samples[-self.policy.window:]
        if len(window) < self.policy.window:
            return None
        metrics = summarize(window)
        breached = (metrics['error_ratio'] >= self.policy.error_ratio or
                    metrics['p95_ms'] >= self.policy.p95_ms)
        clear = metrics['errors'] == 0 and metrics['p95_ms'] < self.policy.p95_ms
        self.breaches = self.breaches + 1 if breached else 0
        self.clears = self.clears + 1 if clear else 0
        transition = None
        if not self.active and self.breaches >= self.policy.fire_windows:
            self.active = True
            transition = 'alert_fired'
        elif self.active and self.clears >= self.policy.clear_windows:
            self.active = False
            transition = 'alert_cleared'
        if transition:
            return {'event': transition, 'window': metrics,
                    'sample_sequence': sample['sequence']}
        return None


def probe(base_url, phase, version, sequence, origin):
    """Measure one real loopback request without using inherited proxy settings.

    Endpoint identity comes only from the owned worker, never from CLI input.
    HTTP errors and connection failures count as observations, rather than being
    dropped from the availability denominator. Timing includes reading the body.
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.monotonic()
    status, body, failure = None, None, None
    try:
        try:
            response = opener.open(base_url + '/health', timeout=2)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.code
            body = json.loads(response.read(1024))
    except (OSError, ValueError, urllib.error.URLError):
        failure = 'transport_or_response_error'
    finished = time.monotonic()
    return {'sequence': sequence, 'phase': phase, 'version': version,
            'started_seconds': round(started - origin, 6),
            'completed_seconds': round(finished - origin, 6),
            'duration_ms': round((finished - started) * 1000, 6),
            'status': status, 'healthy': status == 200 and body == {'status': 'ok'},
            'failure': failure}


def run_lab(interval=0.1):
    """Require baseline, an observed alert, and verified recovery before success.

    Healthy and failed releases run sequentially on different local ports. The
    monitor's rolling window spans these phases, but there is no traffic during
    worker startup/shutdown gaps. Samples therefore are not a production SLO.
    """
    if not math.isfinite(interval) or not 0 <= interval <= 1:
        raise ValueError('Interval must be between 0 and 1 second.')
    started_at = datetime.now(timezone.utc).isoformat()
    origin = time.monotonic()
    monitor, samples, timeline = Monitor(), [], []

    def event(name, **details):
        item = {'event': name, 'elapsed_seconds': round(time.monotonic() - origin, 6),
                **details}
        timeline.append(item)
        return item

    def traffic(url, phase, version, count, stop_on_alert=False):
        for index in range(count):
            if index:
                time.sleep(interval)
            sample = probe(url, phase, version, len(samples) + 1, origin)
            samples.append(sample)
            transition = monitor.observe(sample)
            if transition:
                name = transition.pop('event')
                event(name, **transition)
                if stop_on_alert and name == 'alert_fired':
                    return
        if stop_on_alert:
            raise RuntimeError('The injected incident did not produce the expected alert.')

    with tempfile.TemporaryDirectory(prefix='reliability-lab-') as temporary:
        work = Path(temporary)
        state = work / 'state.json'
        # Synthetic package commit IDs identify fixtures, not real Git history.
        good_zip, good_hash = delivery.build(ROOT, work / 'packages', '1.0.0', 'a' * 40)
        bad_zip, bad_hash = delivery.build(ROOT, work / 'packages', '1.1.0', 'b' * 40)
        good = delivery.promote(good_zip, good_hash, state)['active']
        with running_release(good) as url:
            require_healthy(observe_service(url), '1.0.0')
            event('baseline_started', version='1.0.0')
            traffic(url, 'baseline', '1.0.0', 12)
        if any(not item['healthy'] for item in samples) or monitor.active:
            raise RuntimeError('Baseline was unhealthy or triggered a false alert.')
        event('baseline_verified', measured_requests=12)

        bad = delivery.promote(bad_zip, bad_hash, state)['active']
        with running_release(bad, fail_health=True) as url:
            observations = observe_service(url)
            if observations != {
                'health': {'status': 503, 'body': {'status': 'injected failure'}},
                'version': {'status': 200, 'body': {'version': '1.1.0'}}
            }:
                raise RuntimeError('The intended fault or candidate version was not observed.')
            event('fault_observed', version='1.1.0', injected_behavior='HTTP 503')
            traffic(url, 'incident', '1.1.0', 20, stop_on_alert=True)
            # This is an explicit rehearsal action implementing the documented
            # runbook. The monitoring class itself never performs a rollback.
            event('recovery_started', action='Stop candidate; reverify and restore previous package')

        restored = delivery.rollback(state)['active']
        if restored['version'] != good['version'] or restored['sha256'] != good_hash:
            raise RuntimeError('Rollback did not restore the expected package identity.')
        with running_release(restored) as url:
            require_healthy(observe_service(url), '1.0.0')
            event('restored_service_ready', version='1.0.0')
            traffic(url, 'recovery', '1.0.0', 12)
            require_healthy(observe_service(url), '1.0.0')
            if monitor.active or any(not s['healthy'] for s in samples if s['phase'] == 'recovery'):
                raise RuntimeError('Recovered traffic or alert clearing did not validate.')
            event('recovery_verified', measured_requests=12, version='1.0.0')

    event('cleanup_complete')
    fired = [e for e in timeline if e['event'] == 'alert_fired']
    cleared = [e for e in timeline if e['event'] == 'alert_cleared']
    if len(fired) != 1 or len(cleared) != 1:
        raise RuntimeError('Expected exactly one alert and one clearing transition.')
    times = {item['event']: item['elapsed_seconds'] for item in timeline}
    phases = {name: summarize([s for s in samples if s['phase'] == name])
              for name in ('baseline', 'incident', 'recovery')}
    report = {
        'schema': 'local-reliability-v1', 'result': 'passed',
        'started_at': started_at, 'completed_at': datetime.now(timezone.utc).isoformat(),
        'environment': {'python': platform.python_version(), 'system': platform.system(),
                        'machine': platform.machine()},
        'scope': 'synthetic traffic to sequential disposable loopback workers',
        'provenance': 'unsigned local capture; checksum-only package helpers; synthetic package commit IDs',
        'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in ('reliability_lab.py', 'failure_demo.py', 'demo_service.py',
                                       'delivery.py', 'provenance.py', 'app.py')},
        'policy': asdict(monitor.policy), 'interval_seconds': interval,
        'request_counts_exclude': 'readiness and version checks; worker-transition gaps are unmeasured',
        'phases': phases, 'timeline': timeline,
        'measurements': {
            'observed_fault_to_alert_seconds': round(times['alert_fired'] - times['fault_observed'], 6),
            'alert_to_verified_recovery_seconds': round(times['recovery_verified'] - times['alert_fired'], 6),
            'total_seconds': times['cleanup_complete']},
        'restored_release': {'version': '1.0.0', 'sha256': good_hash},
        'candidate_release': {'version': '1.1.0', 'sha256': bad_hash},
        'cleanup': 'all owned workers stopped; temporary packages and state removed',
    }
    return report, samples


def markdown(report):
    """Human-readable incident evidence uses only values from this capture."""
    lines = ['# Local reliability incident', '',
             f"Recorded: {report['started_at']}", '',
             'Synthetic loopback rehearsal. The candidate worker was configured to return HTTP 503.',
             'The same application bytes are packaged under two fixture versions; this is not an application bug.', '',
             '| Phase | Measured requests | Failed requests | Error ratio | p95 latency (ms) |',
             '| --- | ---: | ---: | ---: | ---: |']
    for name, metrics in report['phases'].items():
        lines.append(f"| {name} | {metrics['requests']} | {metrics['errors']} | {metrics['error_ratio']:.0%} | {metrics['p95_ms']:.3f} |")
    lines += ['', '## Incident timeline', '', '| Elapsed seconds | Observation |', '| ---: | --- |']
    for item in report['timeline']:
        lines.append(f"| {item['elapsed_seconds']:.3f} | {item['event']} |")
    measurements = report['measurements']
    lines += ['', f"Observed fault to alert: {measurements['observed_fault_to_alert_seconds']:.3f} seconds.",
              f"Alert to verified recovery: {measurements['alert_to_verified_recovery_seconds']:.3f} seconds.", '',
              '## Scope and learning', '',
              'The monitor records request outcomes and latency, requires sustained breaches, and clears only after healthy windows.',
              'Recovery revalidates the previous package, its health, its reported version and twelve measured requests.',
              'These are timings for one local rehearsal, not production response targets or an aggregate MTTR.',
              'Readiness/version checks are excluded from traffic counts. No traffic is measured during worker transitions.',
              'There is no cloud deployment, persistent-data recovery, live traffic switching, external paging or attestation verification.',
              'The capture is unsigned. File hashes identify bytes and do not authenticate execution.', '',
              'Cleanup: ' + report['cleanup'] + '.', '']
    return '\n'.join(lines)


def metrics_text(report, samples):
    """Export a final Prometheus-text snapshot, not a live scrape endpoint.

    Outcome counters and cumulative duration counters derive from retained raw
    samples. The p95 field is a gauge for the observed phase, not a histogram.
    """
    lines = ['# HELP lab_http_requests_total Measured synthetic health requests.',
             '# TYPE lab_http_requests_total counter']
    for phase, stats in report['phases'].items():
        for outcome, count in [('success', stats['requests'] - stats['errors']), ('failure', stats['errors'])]:
            lines.append(f'lab_http_requests_total{{phase="{phase}",outcome="{outcome}"}} {count}')
    lines += ['# HELP lab_http_duration_seconds_total Cumulative measured request duration.',
              '# TYPE lab_http_duration_seconds_total counter']
    for phase in report['phases']:
        value = sum(s['duration_ms'] for s in samples if s['phase'] == phase) / 1000
        lines.append(f'lab_http_duration_seconds_total{{phase="{phase}"}} {value:.9f}')
    lines += ['# HELP lab_http_duration_p95_seconds Nearest-rank p95 for this recorded phase.',
              '# TYPE lab_http_duration_p95_seconds gauge']
    for phase, stats in report['phases'].items():
        lines.append(f'lab_http_duration_p95_seconds{{phase="{phase}"}} {stats["p95_ms"] / 1000:.9f}')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        default=Path('reports') / ('reliability-' + uuid.uuid4().hex))
    args = parser.parse_args(argv)
    try:
        # Reserve a new output directory before starting workers. Existing
        # reports are never overwritten, including on a failed attempt.
        args.output_dir.mkdir(parents=True, exist_ok=False)
        report, samples = run_lab()
        content = ''.join(json.dumps(sample, sort_keys=True) + '\n' for sample in samples)
        (args.output_dir / 'samples.jsonl').write_text(content, encoding='utf-8', newline='\n')
        (args.output_dir / 'incident.md').write_text(markdown(report), encoding='utf-8', newline='\n')
        (args.output_dir / 'metrics.prom').write_text(metrics_text(report, samples), encoding='utf-8', newline='\n')
        report['artifact_sha256'] = {name: hashlib.sha256((args.output_dir / name).read_bytes()).hexdigest()
                                     for name in ('samples.jsonl', 'incident.md', 'metrics.prom')}
        delivery.atomic_json(args.output_dir / 'incident.json', report)
        print(f'Reliability lab passed; results: {args.output_dir}')
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f'Reliability lab failed: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
