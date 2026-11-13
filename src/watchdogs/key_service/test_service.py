import os
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from key_service.service import EncryptedKeyStore, GuardianQuorum, LockedError, combine_shares, split_secret


class KeyServiceTests(unittest.TestCase):
    def test_threshold_shares_reconstruct_only_at_threshold(self):
        secret = os.urandom(32)
        shares = split_secret(secret, 3, 5)
        self.assertEqual(combine_shares(shares[:3]), secret)
        with self.assertRaises(Exception):
            combine_shares(shares[:2])

    def test_store_is_locked_until_guardian_quorum_unlocks(self):
        shares = split_secret(os.urandom(32), 3, 5)
        quorum = GuardianQuorum()
        with tempfile.TemporaryDirectory() as directory:
            store = EncryptedKeyStore(os.path.join(directory, "keys.db"), quorum)
            with self.assertRaises(LockedError):
                store.generate("vault-barrier")
            quorum.unlock(shares[:3])
            record = store.generate("vault-barrier")
            encrypted = store.encrypt(record.key_id, b"vault-barrier-material")
            self.assertEqual(store.decrypt(record.key_id, encrypted), b"vault-barrier-material")
            quorum.lock()
            with self.assertRaises(LockedError):
                store.decrypt(record.key_id, encrypted)

    def test_database_does_not_contain_plaintext(self):
        shares = split_secret(os.urandom(32), 3, 5)
        quorum = GuardianQuorum()
        quorum.unlock(shares[:3])
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "keys.db")
            store = EncryptedKeyStore(path, quorum)
            store.generate("vault-barrier")
            with open(path, "rb") as database:
                contents = database.read()
            self.assertNotIn(b"vault-barrier-material", contents)


if __name__ == "__main__":
    unittest.main()
