"""CLI entry point for a bounded observer run."""

from __future__ import annotations

import json
import logging

from orbis.chain.rpc import RpcClient
from orbis.config import Settings
from orbis.observer.indexer import Indexer
from orbis.observer.store import SqliteStore


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format='{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}')
    settings = Settings.from_env()
    rpc = RpcClient(settings.rpc_url, settings.rpc_timeout_seconds, settings.rpc_max_retries)
    if settings.database_url.startswith("sqlite://"):
        store = SqliteStore(settings.database_url.removeprefix("sqlite://"))
    else:
        from orbis.observer.postgres import PostgresStore
        store = PostgresStore(settings.database_url, network_name=settings.network_name,
                              network_environment=settings.network_environment,
                              provider_name=settings.provider_name, runtime_fenced=True)
    try:
        if not settings.database_url.startswith("sqlite://"):
            import os
            store.verify_runtime_principals(
                settings.database_url,
                os.environ.get("ORBIS_MIGRATION_DATABASE_URL", "").strip(),
            )
        if hasattr(store, "check_compatibility"):
            store.check_compatibility()
        result = Indexer(rpc, store, settings.chain_id, settings.confirmation_depth,
                         settings.batch_size).sync(start_block=settings.start_block)
        print(json.dumps(result, sort_keys=True))
    finally:
        store.close()


if __name__ == "__main__":
    main()
