"""Run a disposable, local release-state rehearsal; no cloud deployment occurs."""
import json
from pathlib import Path
import tempfile
from delivery import build, promote, rollback

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    source = Path(__file__).resolve().parent
    state = root / 'state.json'
    # Explicitly synthetic provenance keeps this rehearsal independent of Git.
    first, a = build(source, root, '1.0.0', 'a' * 40)
    second, b = build(source, root, '1.1.0', 'b' * 40)
    promote(first, a, state)
    promote(second, b, state)
    restored = rollback(state)
    if restored['active']['sha256'] != a:
        raise RuntimeError('Rollback did not restore the original artifact.')
    print(json.dumps({'exercise': 'local release-state simulation', 'promoted': '1.1.0', 'restored': restored['active']['version'], 'restored_sha256': a}, indent=2))
