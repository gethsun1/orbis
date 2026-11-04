"""Runtime configuration loaded from the environment."""

from __future__ import annotations

import json
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
    profile_id: str = "default"
    profile_count: int = 1

    @classmethod
    def from_env(cls) -> "Settings":
        raw_profiles = os.environ.get("ORBIS_NETWORKS_JSON")
        legacy_rpc = os.environ.get("ORBIS_RPC_URL", "").strip()
        legacy_chain = os.environ.get("ORBIS_CHAIN_ID", "").strip()
        legacy_present = bool(legacy_rpc or legacy_chain)
        selected_name = os.environ.get("ORBIS_NETWORK", "").strip()
        profiles: list[dict[str, object]]
        if raw_profiles is not None:
            if len(raw_profiles.encode("utf-8")) > 65536:
                raise ValueError("ORBIS_NETWORKS_JSON exceeds the 65536-byte limit")
            try:
                def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
                    result: dict[str, object] = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError("duplicate profile field")
                        result[key] = value
                    return result

                parsed = json.loads(raw_profiles, object_pairs_hook=unique_object)
            except (ValueError, TypeError) as exc:
                raise ValueError("ORBIS_NETWORKS_JSON must contain a valid profile array") from exc
            if not isinstance(parsed, list) or not parsed or len(parsed) > 32:
                raise ValueError("ORBIS_NETWORKS_JSON must contain 1 to 32 profiles")
            profiles = parsed
            names: set[str] = set()
            for profile in profiles:
                supported = {"name", "rpc_url", "chain_id", "network_name", "network_environment", "provider_name"}
                if not isinstance(profile, dict) or set(profile) - supported:
                    raise ValueError("each network profile must be an object with supported fields only")
                name, url, cid = profile.get("name"), profile.get("rpc_url"), profile.get("chain_id")
                if not isinstance(name, str) or not name.strip() or name != name.strip() or name in names:
                    raise ValueError("network profile names must be non-empty and unique")
                if not isinstance(url, str) or not url.strip() or not url.strip().startswith(("http://", "https://")):
                    raise ValueError("network profile rpc_url must use HTTP or HTTPS")
                if isinstance(cid, bool) or not isinstance(cid, int) or cid <= 0:
                    raise ValueError("network profile chain_id must be a positive integer")
                for optional in ("network_name", "network_environment", "provider_name"):
                    if optional in profile and not isinstance(profile[optional], str):
                        raise ValueError(f"network profile {optional} must be a string")
                names.add(name)
            if len(profiles) > 1 and not selected_name:
                raise ValueError("ORBIS_NETWORK must explicitly select a profile when multiple profiles are configured")
            selected_name = selected_name or str(profiles[0]["name"])
            matches = [p for p in profiles if p["name"] == selected_name]
            if len(matches) != 1:
                raise ValueError("ORBIS_NETWORK must name exactly one configured profile")
            profile = matches[0]
            if legacy_present:
                try:
                    legacy_matches = (
                        legacy_rpc == str(profile["rpc_url"]).strip()
                        and int(legacy_chain, 0) == profile["chain_id"]
                    )
                except (ValueError, TypeError):
                    legacy_matches = False
                if not legacy_matches:
                    raise ValueError("legacy RPC settings conflict with selected network profile")
            rpc_url = str(profile["rpc_url"]).strip()
            parsed_chain_id = int(profile["chain_id"])
            profile_id = selected_name
            profile_count = len(profiles)
            network_name = str(profile.get("network_name", "")).strip()
            network_environment = str(profile.get("network_environment", "")).strip()
            provider_name = str(profile.get("provider_name", "")).strip()
        else:
            if not legacy_rpc:
                raise ValueError("ORBIS_RPC_URL must be set")
            if not legacy_chain:
                raise ValueError("ORBIS_CHAIN_ID must be set; do not infer it from the endpoint")
            if selected_name:
                raise ValueError("ORBIS_NETWORK requires ORBIS_NETWORKS_JSON")
            try:
                parsed_chain_id = int(legacy_chain, 0)
            except ValueError as exc:
                raise ValueError("ORBIS_CHAIN_ID must be a decimal or 0x-prefixed integer") from exc
            if parsed_chain_id <= 0:
                raise ValueError("ORBIS_CHAIN_ID must be a positive integer")
            rpc_url = legacy_rpc
            profile_id, profile_count = "default", 1
            network_name = os.environ.get("ORBIS_NETWORK_NAME", "").strip()
            network_environment = os.environ.get("ORBIS_NETWORK_ENVIRONMENT", "").strip()
            provider_name = os.environ.get("ORBIS_PROVIDER_NAME", "").strip()
        database_url = os.environ.get("ORBIS_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("ORBIS_DATABASE_URL must be set")

        def integer(name: str, default: int, minimum: int = 0) -> int:
            value = int(os.environ.get(name, str(default)))
            if value < minimum:
                raise ValueError(f"{name} must be >= {minimum}")
            return value

        start_value = os.environ.get("ORBIS_START_BLOCK", "").strip()
        if database_url.startswith("sqlite://") and profile_count != 1:
            raise ValueError("SQLite supports exactly one configured network profile")
        return cls(
            rpc_url=rpc_url,
            chain_id=parsed_chain_id,
            database_path=os.environ.get("ORBIS_DATABASE_PATH", "./data/orbis.sqlite3"),
            database_url=database_url,
            network_name=network_name,
            network_environment=network_environment,
            provider_name=provider_name,
            start_block=int(start_value, 0) if start_value else None,
            confirmation_depth=integer("ORBIS_CONFIRMATION_DEPTH", 12),
            rpc_timeout_seconds=float(os.environ.get("ORBIS_RPC_TIMEOUT_SECONDS", "15")),
            rpc_max_retries=integer("ORBIS_RPC_MAX_RETRIES", 4),
            batch_size=integer("ORBIS_BATCH_SIZE", 10, 1),
            profile_id=profile_id,
            profile_count=profile_count,
        )
