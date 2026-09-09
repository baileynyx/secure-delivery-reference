"""Deterministic packaging and a local, single-operator release rehearsal.

A checksum detects corruption against a separately trusted digest. It is not a
signature or proof of provenance. Promotion never runs code from an artifact:
the state file records an immutable package identity for an operator to deploy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

COMMIT = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'[0-9a-f]{64}')
VERSION = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+')


def atomic_json(path, value):
    """Replace one state record atomically; no partial JSON on interruption."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.delivery-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def build(source, output, version, commit):
    """Package only the service, with fixed ZIP metadata for reproducibility."""
    if not VERSION.fullmatch(version) or not COMMIT.fullmatch(commit):
        raise ValueError('Use a numeric x.y.z version and a lowercase 40-character source commit.')
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    target = output / f'service-{version}-{commit}.zip'
    manifest = {'version': version, 'source_commit': commit}
    # Exclusive creation prevents a second build from overwriting a release name.
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_STORED) as archive:
        for name, data in [('app.py', (source / 'app.py').read_bytes()), ('manifest.json', (json.dumps(manifest, sort_keys=True) + '\n').encode())]:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest + '\n', encoding='ascii')
    return target, digest


def verify(artifact, expected):
    """Hash the exact bytes, then inspect a tiny allowlisted ZIP structure."""
    artifact = Path(artifact)
    if not DIGEST.fullmatch(expected):
        raise ValueError('Expected digest must contain 64 lowercase hexadecimal characters.')
    if artifact.stat().st_size > 1024 * 1024:
        raise ValueError('Demo package exceeds the 1 MiB size limit.')
    payload = artifact.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError('Artifact digest mismatch; promotion refused.')
    import io
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        if sorted(entry.filename for entry in entries) != ['app.py', 'manifest.json']:
            raise ValueError('Unexpected artifact contents.')
        if any(entry.file_size > 1024 * 1024 for entry in entries):
            raise ValueError('Expanded member exceeds the demo size limit.')
        manifest = json.loads(archive.read('manifest.json'))
        if not isinstance(manifest, dict) or set(manifest) != {'version', 'source_commit'}:
            raise ValueError('Invalid manifest structure.')
        if not isinstance(manifest['version'], str) or not VERSION.fullmatch(manifest['version']):
            raise ValueError('Invalid manifest version.')
        if not isinstance(manifest['source_commit'], str) or not COMMIT.fullmatch(manifest['source_commit']):
            raise ValueError('Invalid manifest commit.')
    return dict(manifest, sha256=expected, artifact=str(artifact.resolve()))


def promote(artifact, expected, state):
    """Record a verified candidate and one previous release for local rollback."""
    candidate = verify(artifact, expected)
    state = Path(state)
    current = json.loads(state.read_text()) if state.exists() else {'active': None, 'previous': None}
    if current.get('active') == candidate:
        return current  # Repeating promotion must not erase the rollback target.
    result = {'active': candidate, 'previous': current['active']}
    atomic_json(state, result)
    return result


def rollback(state):
    """Reverify retained bytes before recording the previous release as active."""
    state = Path(state)
    current = json.loads(state.read_text())
    previous = current.get('previous')
    if not previous:
        raise ValueError('No previous release is available.')
    verified = verify(previous['artifact'], previous['sha256'])
    result = {'active': verified, 'previous': current['active']}
    atomic_json(state, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    package = sub.add_parser('build')
    package.add_argument('--source', type=Path, default=Path('.'))
    package.add_argument('--output', type=Path, default=Path('dist'))
    package.add_argument('--version', required=True)
    package.add_argument('--commit', required=True)
    for verb in ('verify', 'promote'):
        command = sub.add_parser(verb)
        command.add_argument('artifact', type=Path)
        command.add_argument('--sha256', required=True)
        if verb == 'promote': command.add_argument('--state', type=Path, default=Path('runtime/state.json'))
    restore = sub.add_parser('rollback')
    restore.add_argument('--state', type=Path, default=Path('runtime/state.json'))
    args = parser.parse_args()
    try:
        if args.operation == 'build':
            artifact, digest = build(args.source, args.output, args.version, args.commit)
            result = {'artifact': str(artifact), 'sha256': digest}
        elif args.operation == 'verify': result = verify(args.artifact, args.sha256)
        elif args.operation == 'promote': result = promote(args.artifact, args.sha256, args.state)
        else: result = rollback(args.state)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.exit(2, f'Delivery failed: {error}\n')


if __name__ == '__main__': main()
