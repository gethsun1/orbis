"""Pure decoder for the existing standard-shaped ERC-20 Transfer event contract.

This module classifies encoded events only. It does not apply emitter policy or
create findings; those remain gated on owner decisions.
"""
from __future__ import annotations

import re
from typing import Any

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
_HEX_32 = re.compile(r"^0x[0-9a-fA-F]{64}$")
_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ZERO = "0x" + "0" * 40


def _result(log: Any, *, classification: str, validation_status: str,
            diagnostic_code: str | None = None, emitter: str | None = None,
            source_identity: dict | None = None, from_address: str | None = None,
            to_address: str | None = None, amount: str | None = None) -> dict:
    return {
        "classification": classification,
        "validation_status": validation_status,
        "emitter_address": emitter,
        "from_address": from_address,
        "to_address": to_address,
        "amount": amount,
        "diagnostic_code": diagnostic_code,
        "source_identity": source_identity,
        "raw_topics": log.get("topics") if isinstance(log, dict) else None,
        "raw_data": log.get("data") if isinstance(log, dict) else None,
    }


def decode_transfer_log(log: Any) -> dict:
    """Decode one source log without side effects; malformed inputs fail closed."""
    if not isinstance(log, dict):
        return _result({}, classification="invalid", validation_status="invalid", diagnostic_code="invalid_log")
    ident = {key: log.get(key) for key in ("block_number", "block_hash", "transaction_hash", "log_index")}
    complete = (isinstance(ident["block_number"], int) and not isinstance(ident["block_number"], bool) and ident["block_number"] >= 0
                and isinstance(ident["log_index"], int) and not isinstance(ident["log_index"], bool) and ident["log_index"] >= 0
                and isinstance(ident["block_hash"], str) and _HEX_32.fullmatch(ident["block_hash"])
                and isinstance(ident["transaction_hash"], str) and _HEX_32.fullmatch(ident["transaction_hash"]))
    source_identity = ident if complete else None
    emitter = log.get("address")
    if not isinstance(emitter, str) or not _ADDRESS.fullmatch(emitter):
        return _result(log, classification="invalid", validation_status="invalid", diagnostic_code="invalid_emitter_address", source_identity=source_identity)
    emitter = emitter.lower()
    if not complete:
        return _result(log, classification="invalid", validation_status="incomplete", diagnostic_code="missing_source_identity", emitter=emitter)
    topics, data = log.get("topics"), log.get("data")
    if not isinstance(topics, list):
        return _result(log, classification="invalid", validation_status="invalid", diagnostic_code="invalid_topics", emitter=emitter, source_identity=source_identity)
    if not topics:
        return _result(log, classification="invalid", validation_status="invalid", diagnostic_code="invalid_topic_count", emitter=emitter, source_identity=source_identity)
    if not isinstance(topics[0], str) or not _HEX_32.fullmatch(topics[0]):
        return _result(log, classification="invalid", validation_status="invalid", diagnostic_code="invalid_signature_topic", emitter=emitter, source_identity=source_identity)
    if topics[0].lower() != TRANSFER_TOPIC:
        return _result(log, classification="unsupported", validation_status="unsupported", diagnostic_code="unsupported_event_signature", emitter=emitter, source_identity=source_identity)
    if len(topics) != 3:
        return _result(log, classification="invalid", validation_status="invalid", diagnostic_code="invalid_topic_count", emitter=emitter, source_identity=source_identity)
    addresses = []
    for topic in topics[1:]:
        if not isinstance(topic, str) or not _HEX_32.fullmatch(topic):
            return _result(log, classification="invalid", validation_status="invalid", diagnostic_code="invalid_address_topic", emitter=emitter, source_identity=source_identity)
        word = topic[2:]
        if word[:24] != "0" * 24:
            return _result(log, classification="invalid", validation_status="invalid", diagnostic_code="invalid_address_padding", emitter=emitter, source_identity=source_identity)
        addresses.append("0x" + word[24:].lower())
    if not isinstance(data, str) or not _HEX_32.fullmatch(data):
        return _result(log, classification="invalid", validation_status="invalid", diagnostic_code="invalid_uint256_data", emitter=emitter, source_identity=source_identity)
    sender, recipient = addresses
    if sender == _ZERO and recipient == _ZERO:
        classification = "both_zero_unsupported"
    elif sender == _ZERO:
        classification = "mint_zero_amount" if int(data[2:], 16) == 0 else "mint"
    elif recipient == _ZERO:
        classification = "burn_zero_amount" if int(data[2:], 16) == 0 else "burn"
    else:
        classification = "transfer"
    return _result(log, classification=classification, validation_status="valid", emitter=emitter,
                   source_identity=source_identity, from_address=sender, to_address=recipient,
                   amount=str(int(data[2:], 16)))
