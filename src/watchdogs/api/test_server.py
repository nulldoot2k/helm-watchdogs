import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.server import create_server


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.token_path = os.path.join(cls.directory.name, "token")
        with open(cls.token_path, "w", encoding="utf-8") as token_file:
            token_file.write("test-token")
        cls.server = create_server(
            "127.0.0.1",
            0,
            cls.token_path,
            lambda: {
                "status": "healthy",
                "vault": {"sealed": False},
                "incidents": [{"id": "i-1"}],
                "audit": [{"event": "observed"}],
                "diagnostics": {"safe": True},
            },
            ui_enabled=True,
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.directory.cleanup()

    def request(self, path, token=None, method="GET"):
        request = urllib.request.Request(f"{self.base_url}{path}", method=method)
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        return urllib.request.urlopen(request)

    def test_health_does_not_need_authentication(self):
        with self.request("/healthz") as response:
            self.assertEqual(response.status, 200)

    def test_business_api_requires_authentication(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/v1/status")
        self.assertEqual(error.exception.code, 401)

    def test_business_api_returns_operational_state(self):
        with self.request("/v1/vault/health", "test-token") as response:
            self.assertEqual(json.loads(response.read())["sealed"], False)

    def test_mutation_is_blocked_until_policy_engine_exists(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/v1/actions/i-1/execute", "test-token", "POST")
        self.assertEqual(error.exception.code, 403)

    def test_ui_is_static_and_does_not_require_a_token(self):
        with self.request("/ui") as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"Helm Watchdogs", response.read())


if __name__ == "__main__":
    unittest.main()
