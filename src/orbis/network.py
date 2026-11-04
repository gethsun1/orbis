"""Canonical EVM network identity and runtime trust context."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

FINGERPRINT_SCHEME = "evm-genesis-sha256-v1"
_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTEXT_TOKEN = object()


class TrustState(str, Enum):
    UNTRUSTED = "untrusted"
    UNVERIFIED = "untrusted"
    UNRESOLVED = "unresolved"
    VERIFIED = "unresolved"
    TRUSTED = "trusted"
    RESOLVED = "trusted"


def normalize_genesis_hash(value: Any) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise ValueError("genesis hash must be 0x followed by exactly 64 hexadecimal digits")
    return value.lower()


def canonical_identity_bytes(chain_id: int, genesis_hash: str) -> bytes:
    if isinstance(chain_id, bool) or not isinstance(chain_id, int) or chain_id <= 0:
        raise ValueError("chain ID must be a positive integer")
    normalized = normalize_genesis_hash(genesis_hash)
    value = {"chain_id": chain_id, "genesis_hash": normalized}
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def fingerprint(chain_id: int, genesis_hash: str) -> str:
    return "sha256:" + hashlib.sha256(canonical_identity_bytes(chain_id, genesis_hash)).hexdigest()


@dataclass(frozen=True, init=False)
class NetworkContext:
    chain_id: int
    genesis_hash: str | None
    fingerprint_scheme: str | None
    network_fingerprint: str | None
    network_id: int | None
    state: TrustState

    def __init__(self, *, chain_id: int, genesis_hash: str | None,
                 fingerprint_scheme: str | None, network_fingerprint: str | None,
                 network_id: int | None, state: TrustState, _token: object = None) -> None:
        if _token is not _CONTEXT_TOKEN:
            raise TypeError("NetworkContext instances must be created by a verifier or registry resolver")
        if isinstance(chain_id, bool) or not isinstance(chain_id, int) or chain_id <= 0:
            raise ValueError("chain ID must be a positive integer")
        if state is TrustState.UNTRUSTED:
            if any(x is not None for x in (genesis_hash, fingerprint_scheme, network_fingerprint, network_id)):
                raise ValueError("unverified context cannot carry verified identity")
        else:
            normalized = normalize_genesis_hash(genesis_hash)
            if fingerprint_scheme != FINGERPRINT_SCHEME or network_fingerprint != fingerprint(chain_id, normalized):
                raise ValueError("network identity fingerprint does not match canonical identity")
            if state is TrustState.UNRESOLVED and network_id is not None:
                raise ValueError("verified unresolved context cannot carry a network ID")
            if state is TrustState.TRUSTED and (isinstance(network_id, bool) or not isinstance(network_id, int) or network_id <= 0):
                raise ValueError("resolved context requires a positive network ID")
            object.__setattr__(self, "genesis_hash", normalized)
        object.__setattr__(self, "chain_id", chain_id)
        object.__setattr__(self, "fingerprint_scheme", fingerprint_scheme)
        object.__setattr__(self, "network_fingerprint", network_fingerprint)
        object.__setattr__(self, "network_id", network_id)
        object.__setattr__(self, "state", state)

    @classmethod
    def unverified(cls, chain_id: int) -> "NetworkContext":
        return cls(chain_id=chain_id, genesis_hash=None, fingerprint_scheme=None,
                   network_fingerprint=None, network_id=None, state=TrustState.UNTRUSTED,
                   _token=_CONTEXT_TOKEN)


def verified_context(chain_id: int, genesis_hash: str) -> NetworkContext:
    normalized = normalize_genesis_hash(genesis_hash)
    return NetworkContext(chain_id=chain_id, genesis_hash=normalized,
                          fingerprint_scheme=FINGERPRINT_SCHEME,
                          network_fingerprint=fingerprint(chain_id, normalized),
                          network_id=None, state=TrustState.UNRESOLVED, _token=_CONTEXT_TOKEN)


def resolved_context(context: NetworkContext, network_id: int, *,
                     stored_chain_id: int, stored_scheme: str,
                     stored_fingerprint: str, stored_genesis_hash: str) -> NetworkContext:
    if context.state is not TrustState.UNRESOLVED:
        raise ValueError("exact registry resolution requires a verified context")
    stored_genesis = normalize_genesis_hash(stored_genesis_hash)
    if (stored_chain_id != context.chain_id or stored_scheme != context.fingerprint_scheme
            or stored_fingerprint != context.network_fingerprint
            or stored_genesis != context.genesis_hash
            or not _FINGERPRINT_RE.fullmatch(stored_fingerprint)):
        raise ValueError("registered network identity does not match verified RPC identity")
    return NetworkContext(chain_id=context.chain_id, genesis_hash=context.genesis_hash,
                          fingerprint_scheme=context.fingerprint_scheme,
                          network_fingerprint=context.network_fingerprint,
                          network_id=network_id, state=TrustState.TRUSTED, _token=_CONTEXT_TOKEN)
