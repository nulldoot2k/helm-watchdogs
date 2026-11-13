#!/usr/bin/env python3
import threading
import unittest
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class MetricsEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.MetricsHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_health_endpoint_is_lightweight(self):
        with urllib.request.urlopen(f"{self.base_url}/healthz") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"ok\n")

    def test_metrics_endpoint_contains_counters(self):
        app.metric_inc("reconcile_total")
        with urllib.request.urlopen(f"{self.base_url}/metrics") as response:
            body = response.read().decode()
        self.assertIn("watchdogs_info{component=\"controller\"} 1", body)
        self.assertIn("watchdogs_reconcile_total", body)

    def test_unknown_endpoint_is_not_exposed(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"{self.base_url}/debug")
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
