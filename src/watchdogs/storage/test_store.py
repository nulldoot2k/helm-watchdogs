import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage.store import OperationalStore


class OperationalStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = OperationalStore(os.path.join(self.directory.name, "watchdogs.db"))

    def tearDown(self):
        self.directory.cleanup()

    def test_incident_is_idempotent_and_checkpoint_survives_reopen(self):
        first = self.store.upsert_incident("vault-1-unhealthy", "diagnosing", "pod_not_ready", "observe", 1)
        second = self.store.upsert_incident("vault-1-unhealthy", "verifying", "pod_ready", "noop", 2)
        self.assertEqual(first, second)
        self.assertEqual(self.store.get_incident("vault-1-unhealthy")["sequence"], 2)
        self.store.checkpoint("incident:vault-1-unhealthy", "verifying")
        reopened = OperationalStore(self.store.path)
        self.assertEqual(reopened.get_checkpoint("incident:vault-1-unhealthy"), "verifying")

    def test_audit_is_append_only_and_payload_is_json(self):
        incident_id = self.store.upsert_incident("x", "suspected", "test", "observe", 1)
        event_id = self.store.append_audit("decision", {"action": "observe"}, incident_id)
        events = self.store.audit_events(incident_id)
        self.assertEqual(events[0]["event_id"], event_id)
        self.assertEqual(events[0]["payload"], '{"action":"observe"}')
        with sqlite3.connect(self.store.path) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(audit_events)")}
        self.assertIn("payload", columns)


if __name__ == "__main__":
    unittest.main()
