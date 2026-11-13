"""Authenticated native key-service API.

Transport security is supplied by the deployment boundary. Production must
place this service behind mTLS or an equivalent authenticated mesh. The API
returns operation results, never stored key material or guardian shares.
"""

from __future__ import annotations

import hmac
import json
import os
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .service import EncryptedKeyStore, GuardianQuorum, KeyServiceError


class KeyServiceHandler(BaseHTTPRequestHandler):
    token: bytes | None = None
    store: EncryptedKeyStore | None = None
    quorum: GuardianQuorum | None = None

    def _write(self, status, payload):
        body = (json.dumps(payload, sort_keys=True) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self):
        if not self.token:
            return False
        scheme, _, value = self.headers.get("Authorization", "").partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(value.encode(), self.token)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1024 * 1024:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path == "/healthz":
            self._write(200, {"status": "ok", "unlocked": bool(self.quorum and self.quorum.unlocked)})
            return
        if not self._auth():
            self._write(401, {"error": "authentication_required"})
            return
        if self.path == "/v1/status":
            self._write(200, {"unlocked": bool(self.quorum and self.quorum.unlocked)})
            return
        self._write(404, {"error": "not_found"})

    def do_POST(self):
        if not self._auth():
            self._write(401, {"error": "authentication_required"})
            return
        try:
            body = self._body()
            if self.path == "/v1/unlock":
                self.quorum.unlock(body.get("shares", []))
                self._write(200, {"unlocked": True})
                return
            if self.path == "/v1/lock":
                self.quorum.lock()
                self._write(200, {"unlocked": False})
                return
            if self.path == "/v1/keys":
                record = self.store.generate(body["key_id"])
                self._write(201, {"key_id": record.key_id, "version": record.version, "state": record.state})
                return
            if self.path == "/v1/keys/ensure":
                record = self.store.ensure(body["key_id"])
                self._write(200, {"key_id": record.key_id, "version": record.version, "state": record.state})
                return
            if self.path.startswith("/v1/keys/") and self.path.endswith("/encrypt"):
                key_id = self.path.split("/")[3]
                ciphertext = self.store.encrypt(key_id, bytes.fromhex(body["plaintext_hex"]))
                self._write(200, {"ciphertext_hex": ciphertext.hex(), "key_id": key_id, "version": 1})
                return
            if self.path.startswith("/v1/keys/") and self.path.endswith("/decrypt"):
                key_id = self.path.split("/")[3]
                plaintext = self.store.decrypt(key_id, bytes.fromhex(body["ciphertext_hex"]))
                self._write(200, {"plaintext_hex": plaintext.hex(), "key_id": key_id, "version": 1})
                return
            self._write(404, {"error": "not_found"})
        except (KeyError, ValueError, KeyServiceError) as error:
            self._write(400, {"error": str(error)})
        except Exception:
            self._write(500, {"error": "internal_error"})

    def log_message(self, _format, *_args):
        return


def create_server(host, port, token, store, quorum):
    handler = type("ConfiguredKeyServiceHandler", (KeyServiceHandler,), {})
    handler.token = token.encode() if isinstance(token, str) else token
    handler.store = store
    handler.quorum = quorum
    server = ThreadingHTTPServer((host, port), handler)
    cert_file = os.getenv("KEY_SERVICE_TLS_CERT_FILE")
    key_file = os.getenv("KEY_SERVICE_TLS_KEY_FILE")
    ca_file = os.getenv("KEY_SERVICE_TLS_CA_FILE")
    if cert_file or key_file or ca_file:
        if not cert_file or not key_file or not ca_file:
            raise RuntimeError("TLS requires KEY_SERVICE_TLS_CERT_FILE, KEY_SERVICE_TLS_KEY_FILE and KEY_SERVICE_TLS_CA_FILE")
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert_file, key_file)
        context.load_verify_locations(cafile=ca_file)
        context.verify_mode = ssl.CERT_REQUIRED
        server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def read_token(path):
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as token_file:
            return token_file.read().strip()
    except OSError:
        return None


if __name__ == "__main__":
    quorum = GuardianQuorum()
    store = EncryptedKeyStore(os.getenv("WATCHDOGS_KEY_DB", "/var/lib/watchdogs/keys.db"), quorum)
    server = create_server(
        os.getenv("KEY_SERVICE_HOST", "0.0.0.0"),
        int(os.getenv("KEY_SERVICE_PORT", "8090")),
        read_token(os.getenv("WATCHDOGS_KEY_API_TOKEN_FILE")),
        store,
        quorum,
    )
    server.serve_forever()
