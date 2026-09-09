"""Exercise package rejection and HTTP-verified recovery on loopback only.

The three packages are built from this checkout with explicitly synthetic
commit identifiers. This is a trusted local-code exercise, not a sandbox for
arbitrary packages or an Azure deployment adapter. Existing delivery commands
continue to update records only; this harness owns every child process.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

import delivery


ROOT = Path(__file__).resolve().parent


def utc_now():
    """Timestamp observed evidence in UTC without implying a performance target."""
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def running_release(record, fail_health=False):
    """Reverify retained bytes, run their app on loopback, and always reap it.

    Read and hash the exact bytes used for extraction after structural validation
    so a changed file cannot be loaded with a stale expected digest. Extraction
    writes just app.py into a private directory, never arbitrary archive paths.
    """
    artifact = Path(record['artifact'])
    verified = delivery.verify(artifact, record['sha256'])
    if verified != record:
        raise ValueError('Release record differs from the verified package identity.')
    payload = artifact.read_bytes()
    if hashlib.sha256(payload).hexdigest() != record['sha256']:
        raise ValueError('Artifact changed before local service startup.')

    with tempfile.TemporaryDirectory(prefix='delivery-worker-') as temp:
        work = Path(temp)
        app_path = work / 'app.py'
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            app_path.write_bytes(archive.read('app.py'))
        ready = work / 'ready.json'
        command = [sys.executable, str(ROOT / 'demo_service.py'), '--app', str(app_path),
                   '--version', record['version'], '--ready-file', str(ready)]
        if fail_health:
            command.append('--fail-health')
        # No shell parsing or inherited listening address is involved. Logs are
        # kept off pipes to avoid a child blocking on a full output buffer.
        with (work / 'worker.log').open('w+', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=work, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists():
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError('Local service exited during startup: ' + log.read())
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Local service did not become ready within 10 seconds.')
                    time.sleep(0.05)
                port = json.loads(ready.read_text(encoding='utf-8'))['port']
                yield f'http://127.0.0.1:{port}'
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def observe_service(base_url):
    """Record health and version, including non-2xx health bodies as evidence."""
    # Explicitly bypass proxy environment settings for this loopback exercise.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    observations = {}
    for name in ('health', 'version'):
        try:
            response = opener.open(base_url + '/' + name, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            observations[name] = {'status': response.code, 'body': json.load(response)}
    return observations


def require_healthy(observations, version):
    """A health response alone cannot establish that the intended release runs."""
    if observations['health'] != {'status': 200, 'body': {'status': 'ok'}}:
        raise RuntimeError('Local health check failed.')
    if observations['version'] != {'status': 200, 'body': {'version': version}}:
        raise RuntimeError('Local service reported an unexpected version.')


def run_demo():
    """Return evidence only after all scenarios and cleanup complete successfully."""
    started = utc_now()
    scenarios = []
    with tempfile.TemporaryDirectory(prefix='delivery-failure-demo-') as temp:
        work = Path(temp)
        state = work / 'state.json'
        packages = {}
        # These IDs are fixtures, not claimed Git history or signed provenance.
        for version, commit in [('1.0.0', 'a' * 40), ('1.1.0', 'b' * 40), ('1.2.0', 'c' * 40)]:
            packages[version] = delivery.build(ROOT, work / 'packages', version, commit)

        for version in ('1.0.0', '1.1.0'):
            artifact, digest = packages[version]
            release = delivery.promote(artifact, digest, state)['active']
            with running_release(release) as url:
                observed = observe_service(url)
                require_healthy(observed, version)
            scenarios.append({'scenario': 'healthy_release', 'version': version,
                              'sha256': digest, 'observed': observed})

        # Corrupt a separate copy, retaining the original approved build digest.
        # The accepted artifact and the previous rollback package remain intact.
        candidate, candidate_digest = packages['1.2.0']
        tampered = work / 'tampered.zip'
        tampered.write_bytes(candidate.read_bytes() + b'\nintentional-demo-corruption\n')
        before = state.read_bytes()
        try:
            delivery.promote(tampered, candidate_digest, state)
        except ValueError as error:
            if 'digest mismatch' not in str(error):
                raise
            rejection = str(error)
        else:
            raise RuntimeError('Tampered artifact was unexpectedly accepted.')
        if state.read_bytes() != before:
            raise RuntimeError('Rejected artifact changed the release state.')
        scenarios.append({'scenario': 'tampered_artifact', 'promotion': 'rejected',
                          'reason': rejection, 'state_unchanged': True,
                          'active_version': '1.1.0'})

        candidate_record = delivery.promote(candidate, candidate_digest, state)['active']
        # Inject only the candidate worker's health behavior. This is a real
        # HTTP 503 response generated by the harness, not a defective app build.
        with running_release(candidate_record, fail_health=True) as url:
            failed = observe_service(url)
            if failed != {'health': {'status': 503, 'body': {'status': 'injected failure'}},
                          'version': {'status': 200, 'body': {'version': '1.2.0'}}}:
                raise RuntimeError('The intended candidate failure was not observed.')
            try:
                require_healthy(failed, '1.2.0')
            except RuntimeError:
                pass
            else:
                raise RuntimeError('The health gate accepted the failed candidate.')
        # Stop the failed worker before recovery. rollback rechecks the retained
        # previous ZIP; running_release checks it again before executing its app.
        restored = delivery.rollback(state)['active']
        if restored['version'] != '1.1.0' or restored['sha256'] != packages['1.1.0'][1]:
            raise RuntimeError('Recovery did not restore the prior verified identity.')
        with running_release(restored) as url:
            recovered = observe_service(url)
            require_healthy(recovered, '1.1.0')
        scenarios.append({'scenario': 'failed_health_recovery', 'candidate_version': '1.2.0',
                          'candidate_observed': failed, 'restored_version': restored['version'],
                          'restored_sha256': restored['sha256'], 'restored_observed': recovered})

    return {'schema_version': 1, 'result': 'passed', 'scope': 'disposable loopback HTTP rehearsal',
            'provenance': 'synthetic commit identifiers; packages built from local checkout',
            'started_at': started, 'completed_at': utc_now(), 'scenarios': scenarios,
            'cleanup': 'workers stopped; temporary packages and state removed'}


def markdown(report):
    """Render concise observations; JSON retains full statuses, bodies and digests."""
    recovery = report['scenarios'][-1]
    return '\n'.join([
        '# Delivery failure and recovery evidence', '',
        'Scope: disposable loopback HTTP rehearsal; no cloud deployment.', '',
        f"Completed (UTC): {report['completed_at']}", '',
        '| Scenario | Observed outcome |', '| --- | --- |',
        '| Healthy releases | 1.0.0 and 1.1.0 each returned HTTP 200 health and their expected version. |',
        '| Tampered artifact | Digest mismatch blocked promotion; state remained unchanged at 1.1.0. |',
        '| Failed candidate | Harness-injected HTTP 503 at 1.2.0 failed the health gate. |',
        '| Recovery | Retained 1.1.0 was reverified, restarted, and returned HTTP 200 health and version 1.1.0. |',
        '', f"Restored SHA-256: `{recovery['restored_sha256']}`", '',
        'The failed and recovered services were sequential disposable processes on different local ports.',
        'Synthetic commit identifiers are fixtures, not attested provenance. Packages and state were removed after the run.',
        'This does not test production traffic switching, database recovery, concurrency or a cloud deployment adapter.', '',
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, help='Optionally retain JSON and Markdown evidence.')
    args = parser.parse_args(argv)
    try:
        report = run_demo()
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            delivery.atomic_json(args.output_dir / 'evidence.json', report)
            (args.output_dir / 'evidence.md').write_text(markdown(report), encoding='utf-8')
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as error:
        print(f'Failure rehearsal failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
