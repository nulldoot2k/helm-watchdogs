import json
import os
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from key_service.service import EncryptedKeyStore, GuardianQuorum, split_secret
from key_service.server import create_server


class KeyServiceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.TemporaryDirectory()
        cls.quorum = GuardianQuorum()
        cls.shares = split_secret(os.urandom(32), 3, 5)
        cls.store = EncryptedKeyStore(os.path.join(cls.root.name, "keys.db"), cls.quorum)
        cls.server = create_server("127.0.0.1", 0, "api-token", cls.store, cls.quorum)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.root.cleanup()

    def call(self, path, body=None, token="api-token"):
        request = urllib.request.Request(f"{self.base_url}{path}", method="POST")
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Content-Type", "application/json")
        request.data = json.dumps(body or {}).encode()
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())

    def test_key_lifecycle_does_not_return_key_material(self):
        self.call("/v1/unlock", {"shares": self.shares[:3]})
        status, generated = self.call("/v1/keys", {"key_id": "vault-barrier"})
        self.assertEqual(status, 201)
        self.assertNotIn("key", generated)
        _, encrypted = self.call("/v1/keys/vault-barrier/encrypt", {"plaintext_hex": "68656c6c6f"})
        _, decrypted = self.call("/v1/keys/vault-barrier/decrypt", {"ciphertext_hex": encrypted["ciphertext_hex"]})
        self.assertEqual(decrypted["plaintext_hex"], "68656c6c6f")

    def test_unauthenticated_request_is_rejected(self):
        request = urllib.request.Request(f"{self.base_url}/v1/status")
        with self.assertRaises(Exception):
            urllib.request.urlopen(request)


if __name__ == "__main__":
    unittest.main()
