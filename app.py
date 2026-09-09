"""Minimal local demo service; production requires a hardened HTTP server.

The delivery pipeline, not the application, is the subject of this reference.
Health and version responses are intentionally small and deterministic.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os


def response(path):
    if path == '/health':
        return 200, {'status': 'ok'}
    if path == '/version':
        return 200, {'version': os.environ.get('APP_VERSION', 'development')}
    return 404, {'error': 'not found'}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, body = response(self.path)
        encoded = (json.dumps(body, sort_keys=True) + '\n').encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == '__main__':
    # Loopback is the local default. The Dockerfile explicitly selects 0.0.0.0
    # inside its network namespace so the published container port can reach it.
    server = ThreadingHTTPServer((os.environ.get('BIND_ADDRESS', '127.0.0.1'), int(os.environ.get('PORT', '8080'))), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
