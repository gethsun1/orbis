"""Compose persisted canonical logs with the existing D-02 decoder/evidence format.

This is observation-only. It deliberately does not apply emitter policy, create
findings, or activate a rule.
"""
from __future__ import annotations

from orbis.network import NetworkContext, TrustState
from .context import ContextRepository
from .d02_decoder import decode_transfer_log
from .evidence import make_envelope, make_item
from .normalization import digest


def compose_canonical_evidence(db, context: NetworkContext, from_block: int,
                               to_block: int, *, max_diagnostics: int = 100) -> dict:
    if (not isinstance(context, NetworkContext) or context.state is not TrustState.TRUSTED
            or context.network_id is None):
        raise ValueError("canonical evidence requires a trusted resolved NetworkContext")
    if max_diagnostics < 0 or max_diagnostics > 1000:
        raise ValueError("diagnostic bound must be between 0 and 1000")
    registered = db.execute("""SELECT chain_id,fingerprint_scheme,network_fingerprint,genesis_hash
        FROM networks WHERE network_id=%s""", (context.network_id,)).fetchone()
    if registered is None or (registered["chain_id"], registered["fingerprint_scheme"],
            registered["network_fingerprint"], registered["genesis_hash"]) != (
            context.chain_id, context.fingerprint_scheme, context.network_fingerprint,
            context.genesis_hash):
        raise ValueError("NetworkContext does not match the registered canonical identity")

    repo = ContextRepository(db)
    coverage = repo.range_completeness(context.network_id, from_block, to_block)
    decoded, diagnostics = [], []
    diagnostic_total = 0
    for source in repo.logs(context.network_id, from_block, to_block):
        result = decode_transfer_log(source)
        decoded.append((source, result))
        if result["classification"] in {"invalid", "unsupported", "both_zero_unsupported"}:
            diagnostic_total += 1
            if len(diagnostics) < max_diagnostics:
                diagnostics.append({"source_identity": result["source_identity"],
                                    "classification": result["classification"],
                                    "diagnostic_code": result["diagnostic_code"]})
    items = []
    for source, result in decoded:
        raw = {"emitter": source["address"], "topics": source["topics"],
               "data": source["data"], "decoded": result,
               "network_fingerprint": context.network_fingerprint}
        items.append(make_item(network_chain_id=context.chain_id,
            block_number=source["block_number"], block_hash=source["block_hash"],
            transaction_hash=source["transaction_hash"], log_index=source["log_index"],
            source_kind="canonical_transfer_log_observation", normalized_input=raw))
    classifications = [result["classification"] for _, result in decoded]
    status = "insufficient_coverage" if coverage["state"] != "complete" else "available"
    envelope = make_envelope(network_chain_id=context.chain_id,
        bounds={"from": from_block, "to": to_block},
        rule={"rule_id": "D-02", "semantic_version": "decoder-only",
              "definition_digest": digest({"decoder": "exact-transfer-v1", "active": False})},
        parameters={"network_fingerprint": context.network_fingerprint},
        evaluator_build="orbis-canonical-evidence-v1", coverage=coverage, items=items)
    return {"state": status, "coverage": coverage, "envelope": envelope,
            "decoded_count": sum(x in {"mint", "burn", "mint_zero_amount", "burn_zero_amount", "both_zero_unsupported"} for x in classifications),
            "ordinary_count": classifications.count("transfer"),
            "unsupported_count": sum(x in {"unsupported", "both_zero_unsupported"} for x in classifications),
            "malformed_count": classifications.count("invalid"),
            "diagnostics": diagnostics, "diagnostics_truncated": max(0, diagnostic_total - len(diagnostics))}
