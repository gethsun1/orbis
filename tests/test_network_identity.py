from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from orbis.config import Settings
from orbis.network import (
    FINGERPRINT_SCHEME, NetworkContext, TrustState, canonical_identity_bytes,
    fingerprint, resolved_context, verified_context,
)


class NetworkIdentityTests(unittest.TestCase):
    def test_approved_fingerprint_vectors(self):
        vectors = [
            (1, "0x" + "00" * 32,
             b'{"chain_id":1,"genesis_hash":"0x' + b"00" * 32 + b'"}',
             "sha256:22017b203407838f9fe2101dcc049d475cbbe06de31271d96daa0248766c2d2b"),
            (1874, "0x" + "AB" * 32,
             b'{"chain_id":1874,"genesis_hash":"0x' + b"ab" * 32 + b'"}',
             "sha256:2857c5f6e4afba63c90bdc4c9bd1bf86dae54ad9b5b6778c6a7ba8a6b9572923"),
        ]
        for chain_id, genesis, canonical, expected in vectors:
            with self.subTest(chain_id=chain_id):
                self.assertEqual(canonical_identity_bytes(chain_id, genesis), canonical)
                self.assertEqual(fingerprint(chain_id, genesis), expected)
                self.assertEqual(fingerprint(chain_id, genesis), fingerprint(chain_id, genesis))

    def test_rejects_malformed_identity_and_boolean_chain_id(self):
        for value in (None, "", "0x12", "0x" + "g0" * 32, "0X" + "aa" * 32):
            with self.subTest(value=value), self.assertRaises(ValueError):
                fingerprint(1, value)
        for value in (True, 0, -1, 1.0, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_identity_bytes(value, "0x" + "00" * 32)

    def test_same_chain_different_genesis_and_endpoint_independence(self):
        one = verified_context(1874, "0x" + "ab" * 32)
        other = verified_context(1874, "0x" + "cd" * 32)
        same_network_other_endpoint = verified_context(1874, "0x" + "ab" * 32)
        self.assertNotEqual(one.network_fingerprint, other.network_fingerprint)
        self.assertEqual(one.network_fingerprint, same_network_other_endpoint.network_fingerprint)

    def test_trust_states_and_resolver_validation(self):
        with self.assertRaises(TypeError):
            NetworkContext(chain_id=1, genesis_hash=None, fingerprint_scheme=None,
                           network_fingerprint=None, network_id=1, state=TrustState.RESOLVED)
        unresolved = NetworkContext.unverified(1)
        self.assertEqual(unresolved.state, TrustState.UNVERIFIED)
        verified = verified_context(1, "0x" + "00" * 32)
        self.assertEqual(verified.state, TrustState.VERIFIED)
        resolved = resolved_context(verified, 7, stored_chain_id=1,
                                    stored_scheme=FINGERPRINT_SCHEME,
                                    stored_fingerprint=verified.network_fingerprint,
                                    stored_genesis_hash=verified.genesis_hash)
        self.assertEqual((resolved.state, resolved.network_id), (TrustState.RESOLVED, 7))
        with self.assertRaisesRegex(ValueError, "does not match"):
            resolved_context(verified, 7, stored_chain_id=1, stored_scheme=FINGERPRINT_SCHEME,
                             stored_fingerprint="sha256:" + "0" * 64,
                             stored_genesis_hash=verified.genesis_hash)

    def test_legacy_configuration_and_profile_selection(self):
        base = {"ORBIS_DATABASE_URL": "sqlite://:memory:"}
        with patch.dict(os.environ, base, clear=True):
            with self.assertRaisesRegex(ValueError, "ORBIS_RPC_URL"):
                Settings.from_env()
        profiles = '[{"name":"a","rpc_url":"https://one.invalid","chain_id":1},{"name":"b","rpc_url":"https://two.invalid","chain_id":1}]'
        env = {**base, "ORBIS_NETWORKS_JSON": profiles}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "explicitly select"):
                Settings.from_env()
        with patch.dict(os.environ, {**env, "ORBIS_NETWORK": "b"}, clear=True):
            with self.assertRaisesRegex(ValueError, "SQLite supports"):
                Settings.from_env()
        with patch.dict(os.environ, {**env, "ORBIS_NETWORK": "b", "ORBIS_DATABASE_URL": "postgresql://db"}, clear=True):
            settings = Settings.from_env()
        self.assertEqual((settings.profile_id, settings.chain_id, settings.profile_count), ("b", 1, 2))

    def test_rejects_conflicting_profile_and_legacy_configuration(self):
        env = {"ORBIS_DATABASE_URL": "postgresql://db", "ORBIS_NETWORKS_JSON":
               '[{"name":"main","rpc_url":"https://right.invalid","chain_id":1}]',
               "ORBIS_RPC_URL": "https://wrong.invalid", "ORBIS_CHAIN_ID": "1"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "conflict"):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
