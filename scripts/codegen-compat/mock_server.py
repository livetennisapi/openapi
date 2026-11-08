"""A one-endpoint stand-in for the API, for the generated-client smoke calls.

It answers GET /api/public/v1/fixtures with a recorded response
(fixtures.json, the Go client's recorded test data, committed 2026-07-22) and
refuses a request that carries no key, so a client that drops the auth
header fails its smoke call. Every other path is a 404.

    python3 mock_server.py PORT
"""
from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIXTURE = (Path(__file__).resolve().parent / "fixtures.json").read_bytes()
PATH = "/api/public/v1/fixtures"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (http.server names it)
        path = self.path.split("?", 1)[0]
        auth = self.headers.get("Authorization", "") or self.headers.get("X-API-Key", "")
        sent = [h for h in ("Authorization", "X-API-Key") if self.headers.get(h)]
        sys.stderr.write(f"mock: auth headers sent: {','.join(sent) or 'none'}\n")
        if path != PATH:
            self._send(404, b'{"error":"not_found"}')
        elif not auth:
            self._send(401, b'{"error":"unauthorized"}')
        else:
            self._send(200, FIXTURE)

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("mock: " + (fmt % args) + "\n")


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
