from __future__ import annotations

from copy import deepcopy
from typing import Any
from .normalization import digest

SCHEMA_VERSION = 1


def make_item(*, network_chain_id: int, block_number: int, block_hash: str, source_kind: str,
              normalized_input: dict, transaction_hash: str | None = None, log_index: int | None = None) -> dict:
    if block_number < 0 or (log_index is not None and (log_index < 0 or transaction_hash is None)):
        raise ValueError("invalid evidence source identity")
    base = {"network_chain_id":int(network_chain_id),"block_number":int(block_number),"block_hash":block_hash.lower(),
            "transaction_hash":transaction_hash.lower() if transaction_hash else None,"log_index":log_index,
            "source_kind":source_kind,"normalized_input":normalized_input,"digest_algorithm":"sha256","schema_version":SCHEMA_VERSION}
    return {**base,"evidence_digest":digest(base)}


def make_envelope(*, network_chain_id: int, bounds: dict, rule: dict, parameters: dict,
                  evaluator_build: str, coverage: dict, items: list[dict]) -> dict:
    envelope = {"schema_version":SCHEMA_VERSION,"network_chain_id":int(network_chain_id),"bounds":bounds,
                "rule":rule,"parameters":parameters,"evaluator":{"build_identity":evaluator_build},
                "coverage":coverage,"items":items}
    envelope["context_digest"] = digest({"items":items,"bounds":bounds,"network_chain_id":network_chain_id})
    envelope["evidence_digest"] = digest(envelope)
    verify_envelope(envelope)
    return envelope


def verify_envelope(envelope: dict[str, Any]) -> bool:
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported evidence envelope")
    for item in envelope.get("items", []):
        body = {k:v for k,v in item.items() if k != "evidence_digest"}
        if item.get("digest_algorithm") != "sha256" or digest(body) != item.get("evidence_digest"):
            raise ValueError("evidence item digest mismatch")
    body = {k:v for k,v in envelope.items() if k != "evidence_digest"}
    if digest(body) != envelope.get("evidence_digest"): raise ValueError("evidence envelope digest mismatch")
    expected_context = digest({"items":envelope.get("items",[]),"bounds":envelope.get("bounds"),"network_chain_id":envelope.get("network_chain_id")})
    if expected_context != envelope.get("context_digest"): raise ValueError("evidence context digest mismatch")
    return True
