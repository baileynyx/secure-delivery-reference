"""Serve a locally built demo package in a disposable child process.

This harness is used only by failure_demo.py. It loads an already verified,
allowlisted app.py copy and injects the requested health failure without
modifying the release package or adding a failure switch to the actual app.
"""
import argparse
from http.server import ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path

from delivery import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--ready-file', type=Path, required=True)
    parser.add_argument('--fail-health', action='store_true')
    args = parser.parse_args()

    # Each release runs in its own process, so its version cannot leak into
    # another candidate through a shared test process's environment.
    os.environ['APP_VERSION'] = args.version
    spec = importlib.util.spec_from_file_location('packaged_demo_app', args.app)
    application = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(application)

    class DemoHandler(application.Handler):
        def do_GET(self):
            if args.fail_health and self.path == '/health':
                body = (json.dumps({'status': 'injected failure'}) + '\n').encode()
                self.send_response(503)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def log_message(self, format, *args):
            # Evidence is captured by the parent as structured HTTP observations.
            # Suppress routine access logs in the disposable worker process.
            pass

    # Port zero asks the operating system for an unused loopback port. Publish
    # readiness only after binding succeeds; the parent imposes a startup timeout.
    with ThreadingHTTPServer(('127.0.0.1', 0), DemoHandler) as server:
        atomic_json(args.ready_file, {'port': server.server_port})
        server.serve_forever()


if __name__ == '__main__':
    main()
