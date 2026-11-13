"""SQLite operational store used by tests and the local deployment.

The production adapter will use the same repository contract with PostgreSQL.
This store never accepts key material and the audit table has no update or
delete path.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone


class OperationalStore:
    def __init__(self, path: str):
        self.path = path
        self._init_db()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_db(self):
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                  incident_id TEXT PRIMARY KEY,
                  fingerprint TEXT NOT NULL UNIQUE,
                  phase TEXT NOT NULL,
                  reason TEXT NOT NULL,
                  action TEXT NOT NULL,
                  sequence INTEGER NOT NULL DEFAULT 0,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                  name TEXT PRIMARY KEY,
                  value TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                  event_id TEXT PRIMARY KEY,
                  incident_id TEXT,
                  event_type TEXT NOT NULL,
                  payload TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
                );
                """
            )

    def upsert_incident(self, fingerprint, phase, reason, action, sequence):
        now = datetime.now(timezone.utc).isoformat()
        incident_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"helm-watchdogs:{fingerprint}"))
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO incidents
                   (incident_id, fingerprint, phase, reason, action, sequence, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(fingerprint) DO UPDATE SET
                   phase=excluded.phase, reason=excluded.reason, action=excluded.action,
                   sequence=excluded.sequence, updated_at=excluded.updated_at""",
                (incident_id, fingerprint, phase, reason, action, sequence, now),
            )
        return incident_id

    def get_incident(self, fingerprint):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM incidents WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
        return dict(row) if row else None

    def checkpoint(self, name, value):
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO checkpoints(name, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET value=excluded.value,
                   updated_at=excluded.updated_at""",
                (name, value, now),
            )

    def get_checkpoint(self, name):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM checkpoints WHERE name=?", (name,)
            ).fetchone()
        return row["value"] if row else None

    def append_audit(self, event_type, payload, incident_id=None):
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
                (event_id, incident_id, event_type, encoded, now),
            )
        return event_id

    def audit_events(self, incident_id=None):
        query = "SELECT * FROM audit_events"
        params = ()
        if incident_id:
            query += " WHERE incident_id=?"
            params = (incident_id,)
        query += " ORDER BY created_at, event_id"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]
