import unittest
from decimal import Decimal
from orbis.rules.coverage import assess_coverage, gate_outcome
from orbis.rules.evidence import make_envelope, make_item, verify_envelope
from orbis.rules.identity import evaluation_identity
from orbis.rules.normalization import digest, normalize_parameters


class RuleInfrastructureTests(unittest.TestCase):
    def test_parameter_normalization_and_canonical_identity(self):
        schema={"properties":{"owner":{"format":"address"},"amount":{"type":"integer"},"tags":{"type":"array","x-collection":"set"}}}
        a=normalize_parameters({"owner":"0x"+"AB"*20,"amount":2**70,"tags":["b","a","a"]},schema)
        b=normalize_parameters({"tags":["a","b"],"amount":str(2**70),"owner":"0x"+"ab"*20},schema)
        self.assertEqual(a,b)
        kwargs=dict(chain_id=1874,subject_kind="address",subject_key="0x"+"ab"*20,rule_id="D-01",semantic_version="1.0.0",definition_digest=digest({"rule":1}),
            from_block=1,to_block=2,parameters=a,context_digest=digest({"x":1}),evaluator_build="build")
        self.assertEqual(evaluation_identity(**kwargs),evaluation_identity(**kwargs))
        self.assertNotEqual(evaluation_identity(**kwargs),evaluation_identity(**{**kwargs,"to_block":3}))

    def test_v1_characterizes_same_chain_id_network_fingerprint_collision(self):
        """v1 currently ignores network fingerprints; preserve this reproducer until v2 replaces it."""
        common=dict(chain_id=1874,subject_kind="address",subject_key="0x"+"ab"*20,
            rule_id="D-01",semantic_version="1.0.0",definition_digest=digest({"rule":1}),
            from_block=1,to_block=2,parameters={},context_digest=digest({"shared_context":True}),evaluator_build="build")
        network_a={"chain_id":1874,"genesis_hash":"0x"+"11"*32}
        network_b={"chain_id":1874,"genesis_hash":"0x"+"22"*32}
        # Each identity is passed as the current API's only network field. Since
        # both networks have the same chain ID, v1 emits the same key despite
        # their distinct canonical genesis hashes.
        self.assertNotEqual(network_a["genesis_hash"],network_b["genesis_hash"])
        key_a=evaluation_identity(**{**common,"chain_id":network_a["chain_id"]})
        key_b=evaluation_identity(**{**common,"chain_id":network_b["chain_id"]})
        self.assertEqual(key_a,key_b)

    def test_v2_distinguishes_networks_sharing_chain_id(self):
        """Portable v2 identity separates networks sharing one chain ID."""
        common=dict(chain_id=1874,subject_kind="address",subject_key="0x"+"ab"*20,
            rule_id="D-01",semantic_version="1.0.0",definition_digest=digest({"rule":1}),
            from_block=1,to_block=2,parameters={},context_digest=digest({"shared_context":True}),evaluator_build="build")
        first=evaluation_identity(**common,network_fingerprint="genesis:0x"+"11"*32)
        second=evaluation_identity(**common,network_fingerprint="genesis:0x"+"22"*32)
        self.assertNotEqual(first,second)

    def test_decimal_null_omitted_and_set_behavior(self):
        schema={"properties":{"ratio":{"type":"number"},"optional":{}}}
        self.assertEqual(normalize_parameters({"ratio":Decimal("1.2500"),"optional":None},schema),{"ratio":"1.25","optional":None})
        self.assertEqual(normalize_parameters({},schema),{})

    def test_coverage_gates_negative_result(self):
        coverage=assess_coverage({"receipts":"complete","logs":"partial"},["receipts","logs"])
        self.assertEqual(gate_outcome("not_matched",coverage),"insufficient_coverage")
        self.assertEqual(gate_outcome("not_matched",assess_coverage({"receipts":"complete"},["receipts"])),"not_matched")

    def test_evidence_snapshot_verification_and_tamper_detection(self):
        item=make_item(network_chain_id=1874,block_number=5,block_hash="0xblock",transaction_hash="0xtx",log_index=2,source_kind="receipt_log",normalized_input={"data":"0x01"})
        env=make_envelope(network_chain_id=1874,bounds={"from":5,"to":5},rule={"rule_id":"D-01","version":"0.1.0"},parameters={},evaluator_build="git:abc",coverage={},items=[item])
        self.assertTrue(verify_envelope(env))
        changed={**env,"items":[{**item,"normalized_input":{"data":"0x02"}}]}
        with self.assertRaises(ValueError): verify_envelope(changed)


if __name__ == "__main__": unittest.main()
