"""Runtime configuration loaded from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    rpc_url: str
    chain_id: int
    database_path: str
    database_url: str
    network_name: str
    network_environment: str
    provider_name: str
    start_block: int | None
    confirmation_depth: int
    rpc_timeout_seconds: float
    rpc_max_retries: int
    batch_size: int

    @classmethod
    def from_env(cls) -> "Settings":
        rpc_url = os.environ.get("ORBIS_RPC_URL", "").strip()
        chain_id = os.environ.get("ORBIS_CHAIN_ID", "").strip()
        if not rpc_url:
            raise ValueError("ORBIS_RPC_URL must be set")
        if not chain_id:
            raise ValueError("ORBIS_CHAIN_ID must be set; do not infer it from the endpoint")
        database_url = os.environ.get("ORBIS_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("ORBIS_DATABASE_URL must be set")
        try:
            parsed_chain_id = int(chain_id, 0)
        except ValueError as exc:
            raise ValueError("ORBIS_CHAIN_ID must be a decimal or 0x-prefixed integer") from exc

        def integer(name: str, default: int, minimum: int = 0) -> int:
            value = int(os.environ.get(name, str(default)))
            if value < minimum:
                raise ValueError(f"{name} must be >= {minimum}")
            return value

        start_value = os.environ.get("ORBIS_START_BLOCK", "").strip()
        return cls(
            rpc_url=rpc_url,
            chain_id=parsed_chain_id,
            database_path=os.environ.get("ORBIS_DATABASE_PATH", "./data/orbis.sqlite3"),
            database_url=database_url,
            network_name=os.environ.get("ORBIS_NETWORK_NAME", "").strip(),
            network_environment=os.environ.get("ORBIS_NETWORK_ENVIRONMENT", "").strip(),
            provider_name=os.environ.get("ORBIS_PROVIDER_NAME", "").strip(),
            start_block=int(start_value, 0) if start_value else None,
            confirmation_depth=integer("ORBIS_CONFIRMATION_DEPTH", 12),
            rpc_timeout_seconds=float(os.environ.get("ORBIS_RPC_TIMEOUT_SECONDS", "15")),
            rpc_max_retries=integer("ORBIS_RPC_MAX_RETRIES", 4),
            batch_size=integer("ORBIS_BATCH_SIZE", 10, 1),
        )
