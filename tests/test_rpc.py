from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from orbis.chain.rpc import RpcClient, RpcError


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class RpcClientTests(unittest.TestCase):
    def test_reads_result_and_converts_chain_id(self):
        with patch("urllib.request.urlopen", return_value=Response({"jsonrpc": "2.0", "id": 1,
                                                                    "result": "0x753"})):
            self.assertEqual(RpcClient("https://rpc.example").chain_id(), 1875)

    def test_retries_http_rate_limit(self):
        rate_limited = urllib.error.HTTPError("https://rpc.example", 429, "busy", {}, io.BytesIO())
        with patch("urllib.request.urlopen", side_effect=[rate_limited,
                Response({"jsonrpc": "2.0", "id": 1, "result": "0x2"})]) as request, \
             patch("orbis.chain.rpc.time.sleep"):
            self.assertEqual(RpcClient("https://rpc.example", max_retries=1).chain_id(), 2)
            self.assertEqual(request.call_count, 2)

    def test_does_not_retry_forbidden_and_does_not_echo_endpoint(self):
        forbidden = urllib.error.HTTPError("https://user:secret@rpc.example/key", 403,
                                            "forbidden", {}, io.BytesIO())
        with patch("urllib.request.urlopen", side_effect=forbidden) as request:
            with self.assertRaisesRegex(RpcError, "HTTP 403") as error:
                RpcClient("https://rpc.example", max_retries=3).chain_id()
            self.assertEqual(request.call_count, 1)
            self.assertNotIn("secret", str(error.exception))


if __name__ == "__main__":
    unittest.main()
