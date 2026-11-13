"""Small native key service with threshold bootstrap and encrypted storage.

The database never receives plaintext key material. The guardian root key is
reconstructed only after a threshold of operator shares is supplied and is
kept only in process memory until the quorum is locked again.
"""

from __future__ import annotations

import base64
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


class KeyServiceError(Exception):
    """Base error for key service failures."""


class LockedError(KeyServiceError):
    """Raised when an operation is attempted without guardian quorum."""


class InvalidShare(KeyServiceError):
    """Raised when a guardian share is malformed or inconsistent."""


def _gf_mul(left: int, right: int) -> int:
    result = 0
    for _ in range(8):
        if right & 1:
            result ^= left
        high = left & 0x80
        left = (left << 1) & 0xFF
        if high:
            left ^= 0x1B
        right >>= 1
    return result


def _gf_pow(value: int, exponent: int) -> int:
    result = 1
    while exponent:
        if exponent & 1:
            result = _gf_mul(result, value)
        value = _gf_mul(value, value)
        exponent >>= 1
    return result


def _gf_inv(value: int) -> int:
    if value == 0:
        raise InvalidShare("share coordinates must be unique")
    return _gf_pow(value, 254)


def _eval_polynomial(coefficients: list[int], x: int) -> int:
    result = 0
    for coefficient in reversed(coefficients):
        result = _gf_mul(result, x) ^ coefficient
    return result


def split_secret(secret: bytes, threshold: int, share_count: int) -> list[str]:
    """Split bytes into Shamir shares over GF(256)."""
    if not secret:
        raise ValueError("secret cannot be empty")
    if threshold < 2 or share_count < threshold or share_count > 255:
        raise ValueError("require 2 <= threshold <= share_count <= 255")
    coefficients = [
        [byte] + [secrets.randbelow(256) for _ in range(threshold - 1)]
        for byte in secret
    ]
    shares = []
    for x in range(1, share_count + 1):
        payload = bytes(_eval_polynomial(row, x) for row in coefficients)
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        shares.append(f"v1:{threshold}:{x}:{encoded}")
    return shares


def combine_shares(shares: list[str]) -> bytes:
    """Reconstruct a secret from a threshold set of shares."""
    if not shares:
        raise InvalidShare("at least one share is required")
    parsed = []
    for share in shares:
        try:
            version, threshold_text, x_text, encoded = share.split(":", 3)
            threshold = int(threshold_text)
            x = int(x_text)
            payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except (ValueError, TypeError) as exc:
            raise InvalidShare("malformed guardian share") from exc
        if version != "v1" or not 1 <= x <= 255:
            raise InvalidShare("unsupported guardian share")
        parsed.append((threshold, x, payload))
    threshold = parsed[0][0]
    if len(parsed) < threshold or any(item[0] != threshold for item in parsed):
        raise InvalidShare("guardian threshold has not been met")
    if len({item[1] for item in parsed}) != len(parsed):
        raise InvalidShare("duplicate guardian share")
    length = len(parsed[0][2])
    if any(len(item[2]) != length for item in parsed):
        raise InvalidShare("guardian share lengths differ")
    result = bytearray(length)
    for index, (_threshold, x_j, payload_j) in enumerate(parsed):
        coefficient = 1
        for other_index, (_other_threshold, x_m, _other_payload) in enumerate(parsed):
            if index == other_index:
                continue
            coefficient = _gf_mul(coefficient, _gf_mul(x_m, _gf_inv(x_m ^ x_j)))
        for offset, value in enumerate(payload_j):
            result[offset] ^= _gf_mul(value, coefficient)
    return bytes(result)


@dataclass(frozen=True)
class KeyRecord:
    key_id: str
    version: int
    state: str


class GuardianQuorum:
    """In-memory guardian unlock state."""

    def __init__(self):
        self._root_key: bytearray | None = None

    @property
    def unlocked(self) -> bool:
        return self._root_key is not None

    def unlock(self, shares: list[str]) -> None:
        root = combine_shares(shares)
        if len(root) < 32:
            raise InvalidShare("guardian root key is too short")
        self._root_key = bytearray(root)

    def lock(self) -> None:
        if self._root_key is not None:
            for index in range(len(self._root_key)):
                self._root_key[index] = 0
        self._root_key = None

    def wrapping_key(self) -> bytes:
        if self._root_key is None:
            raise LockedError("guardian quorum is locked")
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"helm-watchdogs/grk/v1",
            info=b"watchdogs-key-encryption-key",
        ).derive(bytes(self._root_key))


class EncryptedKeyStore:
    """SQLite operational store containing ciphertext only."""

    def __init__(self, path: str, quorum: GuardianQuorum):
        self.path = path
        self.quorum = quorum
        self._init_db()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_db(self):
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS key_records ("
                "key_id TEXT NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL, "
                "nonce BLOB NOT NULL, ciphertext BLOB NOT NULL, created_at TEXT NOT NULL, "
                "PRIMARY KEY (key_id, version))"
            )

    def _seal(self, key_id: str, version: int, value: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        aad = f"{key_id}:{version}".encode()
        ciphertext = AESGCM(self.quorum.wrapping_key()).encrypt(nonce, value, aad)
        return nonce, ciphertext

    def _open(self, key_id: str, version: int, nonce: bytes, ciphertext: bytes) -> bytes:
        aad = f"{key_id}:{version}".encode()
        return AESGCM(self.quorum.wrapping_key()).decrypt(nonce, ciphertext, aad)

    def generate(self, key_id: str) -> KeyRecord:
        if not key_id or len(key_id) > 256:
            raise KeyServiceError("invalid key id")
        key = secrets.token_bytes(32)
        nonce, ciphertext = self._seal(key_id, 1, key)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO key_records VALUES (?, ?, ?, ?, ?, ?)",
                (key_id, 1, "active", nonce, ciphertext, datetime.now(timezone.utc).isoformat()),
            )
        return KeyRecord(key_id, 1, "active")

    def ensure(self, key_id: str) -> KeyRecord:
        """Create the wrapping key once, without ever returning key material."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT version, state FROM key_records WHERE key_id=? ORDER BY version DESC LIMIT 1",
                (key_id,),
            ).fetchone()
        if row is not None:
            return KeyRecord(key_id, row[0], row[1])
        return self.generate(key_id)

    def _load(self, key_id: str, version: int = 1) -> bytes:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT nonce, ciphertext, state FROM key_records WHERE key_id=? AND version=?",
                (key_id, version),
            ).fetchone()
        if row is None:
            raise KeyServiceError("key not found")
        if row[2] != "active":
            raise KeyServiceError("key is not active")
        return self._open(key_id, version, row[0], row[1])

    def encrypt(self, key_id: str, plaintext: bytes, version: int = 1) -> bytes:
        key = self._load(key_id, version)
        nonce = os.urandom(12)
        aad = f"operation:{key_id}:{version}".encode()
        return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)

    def decrypt(self, key_id: str, ciphertext: bytes, version: int = 1) -> bytes:
        if len(ciphertext) < 13:
            raise KeyServiceError("ciphertext is too short")
        key = self._load(key_id, version)
        nonce, payload = ciphertext[:12], ciphertext[12:]
        aad = f"operation:{key_id}:{version}".encode()
        return AESGCM(key).decrypt(nonce, payload, aad)
