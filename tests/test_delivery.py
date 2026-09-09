"""Verify HTTP behavior and failure paths that could corrupt release state."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
from http.server import ThreadingHTTPServer
import app
import delivery


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state.json'
        self.source = Path(__file__).resolve().parents[1]

    def build(self, version='1.0.0', folder='dist'):
        # Synthetic commit identifiers are test fixtures, never claimed as history.
        return delivery.build(self.source, self.root / folder, version, 'a' * 40)

    def test_reproducible_bytes(self):
        first, a = self.build(folder='a')
        second, b = self.build(folder='b')
        self.assertEqual(a, b)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_existing_artifact_cannot_be_overwritten(self):
        self.build()
        with self.assertRaises(FileExistsError): self.build()

    def test_tampered_artifact_preserves_state(self):
        first, digest = self.build()
        delivery.promote(first, digest, self.state)
        before = self.state.read_bytes()
        first.write_bytes(first.read_bytes() + b'tampered')
        with self.assertRaises(ValueError): delivery.promote(first, digest, self.state)
        self.assertEqual(before, self.state.read_bytes())

    def test_round_trip_rollback(self):
        first, a = self.build()
        second, b = self.build('1.1.0')
        delivery.promote(first, a, self.state)
        delivery.promote(second, b, self.state)
        self.assertEqual(delivery.rollback(self.state)['active']['sha256'], a)

    def test_repeat_promotion_preserves_previous(self):
        first, a = self.build()
        second, b = self.build('1.1.0')
        delivery.promote(first, a, self.state)
        delivery.promote(second, b, self.state)
        delivery.promote(second, b, self.state)
        self.assertEqual(delivery.rollback(self.state)['active']['sha256'], a)

    def test_rollback_rejects_corrupted_previous(self):
        first, a = self.build()
        second, b = self.build('1.1.0')
        delivery.promote(first, a, self.state)
        delivery.promote(second, b, self.state)
        before = self.state.read_bytes()
        first.write_bytes(b'corrupt')
        with self.assertRaises(ValueError): delivery.rollback(self.state)
        self.assertEqual(before, self.state.read_bytes())

    def test_no_previous_release(self):
        first, a = self.build()
        delivery.promote(first, a, self.state)
        with self.assertRaises(ValueError): delivery.rollback(self.state)

    def test_invalid_release_metadata(self):
        for version, commit in [('../escape', 'a' * 40), ('1.0.0', 'main')]:
            with self.subTest(version=version, commit=commit):
                with self.assertRaises(ValueError): delivery.build(self.source, self.root, version, commit)

    def test_version_and_unknown_route(self):
        with patch.dict('os.environ', {'APP_VERSION': '1.2.3'}):
            self.assertEqual(app.response('/version'), (200, {'version': '1.2.3'}))
        self.assertEqual(app.response('/missing')[0], 404)

    def test_actual_http_health(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/health', timeout=3) as result:
                self.assertEqual(json.load(result), {'status': 'ok'})
                self.assertEqual(result.headers['Cache-Control'], 'no-store')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__': unittest.main()
