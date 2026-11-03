from __future__ import annotations

from .normalization import digest, normalize_subject


def evaluation_identity(*, chain_id: int, subject_kind: str, subject_key: str, rule_id: str,
                        semantic_version: str, definition_digest: str,
                        from_block: int, to_block: int, parameters: dict, context_digest: str,
                        evaluator_build: str) -> str:
    if from_block < 0 or to_block < from_block: raise ValueError("invalid explicit block bounds")
    subject_key = normalize_subject(subject_kind, subject_key)
    return digest({"algorithm":"orbis-evaluation-v1", "network":{"chain_id":int(chain_id)},
        "subject":{"kind":subject_kind,"key":subject_key},
        "rule_version":{"rule_id":rule_id,"semantic_version":semantic_version,"definition_digest":definition_digest},
        "bounds":{"from":int(from_block),"to":int(to_block)}, "parameters":parameters,
        "context_digest":context_digest, "evaluator_build":evaluator_build})


def finding_identity(result: dict) -> str:
    return digest({"algorithm":"orbis-finding-v1","result":result})
