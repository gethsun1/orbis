from __future__ import annotations

import unittest
from orbis.rules.d02_decoder import TRANSFER_TOPIC, decode_transfer_log

ZERO = "0x" + "0" * 40
A = "0x" + "11" * 20
B = "0x" + "22" * 20


def topic(address): return "0x" + "0" * 24 + address[2:]


def log(sender=ZERO, recipient=B, amount=7, *, topics=None, data=None, **overrides):
    result = {"block_number": 12, "block_hash": "0x" + "ab" * 32,
              "transaction_hash": "0x" + "cd" * 32, "log_index": 3,
              "address": A, "topics": topics or [TRANSFER_TOPIC, topic(sender), topic(recipient)],
              "data": data or "0x" + f"{amount:064x}"}
    result.update(overrides)
    return result


class D02DecoderTests(unittest.TestCase):
    def test_classifies_shapes_and_keeps_amount_as_decimal(self):
        self.assertEqual(decode_transfer_log(log())["classification"], "mint")
        self.assertEqual(decode_transfer_log(log(sender=A, recipient=ZERO))["classification"], "burn")
        self.assertEqual(decode_transfer_log(log(sender=A, recipient=B))["classification"], "transfer")
        self.assertEqual(decode_transfer_log(log(amount=0))["classification"], "mint_zero_amount")
        self.assertEqual(decode_transfer_log(log(sender=A, recipient=ZERO, amount=0))["classification"], "burn_zero_amount")
        self.assertEqual(decode_transfer_log(log(sender=ZERO, recipient=ZERO))["classification"], "both_zero_unsupported")
        self.assertEqual(decode_transfer_log(log(amount=2**256-1))["amount"], str(2**256-1))

    def test_keeps_multiple_logs_separate_and_is_deterministic(self):
        logs = [log(log_index=i) for i in (1, 2)]
        first = [decode_transfer_log(item) for item in logs]
        self.assertEqual(first, [decode_transfer_log(item) for item in logs])
        self.assertNotEqual(first[0]["source_identity"], first[1]["source_identity"])
        self.assertEqual(first[0]["raw_topics"], logs[0]["topics"])

    def test_malformed_inputs_fail_closed_with_stable_codes(self):
        cases = [
            (log(topics=[TRANSFER_TOPIC, topic(ZERO)]), "invalid_topic_count"),
            (log(topics=[TRANSFER_TOPIC, "0x" + "01" * 12 + "11" * 20, topic(B)]), "invalid_address_padding"),
            (log(data="0x12"), "invalid_uint256_data"),
            (log(data="0x" + "g" * 64), "invalid_uint256_data"),
            (log(topics=[TRANSFER_TOPIC, topic(ZERO), topic(B), topic(A)]), "invalid_topic_count"),
            (log(address="0x1234"), "invalid_emitter_address"),
        ]
        for item, code in cases:
            with self.subTest(code=code):
                result = decode_transfer_log(item)
                self.assertEqual(result["validation_status"], "invalid")
                self.assertEqual(result["diagnostic_code"], code)
                self.assertIsNone(result["amount"])

    def test_unsupported_signature_and_missing_identity_are_diagnostics(self):
        item = log(topics=["0x" + "00" * 32, topic(ZERO), topic(B)])
        self.assertEqual(decode_transfer_log(item)["validation_status"], "unsupported")
        missing = log()
        del missing["transaction_hash"]
        result = decode_transfer_log(missing)
        self.assertEqual(result["diagnostic_code"], "missing_source_identity")
        self.assertIsNone(result["source_identity"])


if __name__ == "__main__": unittest.main()
