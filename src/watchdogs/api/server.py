"""Small authenticated API for UI, CLI, and read-only diagnostics.

The API intentionally exposes operational state, not key material. Health and
metrics are unauthenticated for Kubernetes probes and scraping. All business
endpoints require a bearer token supplied through a mounted file.
"""

from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


SAFE_EMPTY_STATE = {
    "status": "unknown",
    "incidents": [],
    "audit": [],
    "diagnostics": {"message": "controller state is not initialized"},
}

UI_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Helm Watchdogs</title><style>body{font:15px system-ui;margin:2rem;max-width:960px}pre{background:#f4f4f4;padding:1rem;overflow:auto}button{padding:.5rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}.card{border:1px solid #ddd;border-radius:8px;padding:1rem}</style></head>
<body><h1>Helm Watchdogs</h1><p>Vault operations dashboard</p>
<label>API token <input id="token" type="password" autocomplete="off"></label> <button onclick="loadState()">Refresh</button>
<div class="grid"><div class="card"><h2>Status</h2><pre id="status">Not loaded</pre></div><div class="card"><h2>Vault</h2><pre id="vault">Not loaded</pre></div><div class="card"><h2>Diagnostics</h2><pre id="diagnostics">Not loaded</pre></div></div>
<script>async function loadState(){const token=document.getElementById('token').value;const h={Authorization:'Bearer '+token};for(const n of ['status','vault/health','diagnostics']){const r=await fetch('/v1/'+n,{headers:h});document.getElementById(n.replace('/','')).textContent=JSON.stringify(await r.json(),null,2)}}
</script></body></html>"""


class ApiHandler(BaseHTTPRequestHandler):
    state_provider: Callable[[], dict] = lambda: SAFE_EMPTY_STATE
    token: bytes | None = None
    ui_enabled = False

    def _write(self, status: int, payload: dict):
        body = (json.dumps(payload, sort_keys=True) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if not self.token:
            return False
        header = self.headers.get("Authorization", "")
        scheme, _, value = header.partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(value.encode(), self.token)

    def _write_ui(self):
        body = UI_HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/ui") and self.ui_enabled:
            self._write_ui()
            return
        if self.path == "/healthz":
            self._write(200, {"status": "ok"})
            return
        if self.path == "/metrics":
            self._write(200, {"status": "ok"})
            return
        if not self._authorized():
            self._write(401, {"error": "authentication_required"})
            return
        state = self.state_provider()
        routes = {
            "/v1/status": lambda: {"status": state.get("status", "unknown")},
            "/v1/vault/health": lambda: state.get("vault", {"status": "unknown"}),
            "/v1/incidents": lambda: {"incidents": state.get("incidents", [])},
            "/v1/audit": lambda: {"audit": state.get("audit", [])},
            "/v1/diagnostics": lambda: state.get("diagnostics", {}),
        }
        if self.path not in routes:
            self._write(404, {"error": "not_found"})
            return
        self._write(200, routes[self.path]())

    def do_POST(self):
        if not self._authorized():
            self._write(401, {"error": "authentication_required"})
            return
        self._write(403, {"error": "mutating_actions_require_policy_engine"})

    def log_message(self, _format, *_args):
        return


def load_token(path: str | None) -> bytes | None:
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as token_file:
            token = token_file.read().strip().encode()
    except OSError:
        return None
    return token or None


def create_server(host: str, port: int, token_file: str | None, state_provider, ui_enabled=False):
    handler = type("ConfiguredApiHandler", (ApiHandler,), {})
    handler.token = load_token(token_file)
    handler.state_provider = staticmethod(state_provider)
    handler.ui_enabled = ui_enabled
    return ThreadingHTTPServer((host, port), handler)


if __name__ == "__main__":
    server = create_server(
        os.getenv("API_HOST", "127.0.0.1"),
        int(os.getenv("API_PORT", "8081")),
        os.getenv("WATCHDOGS_API_TOKEN_FILE"),
        lambda: SAFE_EMPTY_STATE,
        os.getenv("UI_ENABLED", "false").lower() == "true",
    )
    server.serve_forever()
