"""CLI entry point for a bounded observer run."""

from __future__ import annotations

import json
import logging
import argparse

from orbis.chain.rpc import RpcClient
from orbis.config import Settings
from orbis.observer.indexer import Indexer
from orbis.observer.store import SqliteStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded ORBIS observer pass")
    parser.add_argument("--start-block", type=int, help="inclusive start block for this pass")
    parser.add_argument("--end-block", type=int, help="inclusive end block for this pass")
    args = parser.parse_args()
    if (args.start_block is None) != (args.end_block is None):
        parser.error("--start-block and --end-block must be supplied together")
    if args.start_block is not None and (args.start_block < 0 or args.end_block < args.start_block):
        parser.error("block range must be non-negative and inclusive end must be >= start")
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
        indexer = Indexer(rpc, store, settings.chain_id, settings.confirmation_depth, settings.batch_size)
        result = indexer.sync(start_block=args.start_block if args.start_block is not None else settings.start_block,
                              end_block=args.end_block)
        context = indexer.network_context
        result["profile"] = settings.profile_id
        result["network_fingerprint"] = context.network_fingerprint if context else None
        if args.start_block is not None and args.end_block is not None and context is not None:
            result["requested_range"] = {"start": args.start_block, "end": args.end_block}
            if not settings.database_url.startswith("sqlite://") and context.network_id is not None:
                from orbis.rules.context import ContextRepository
                coverage = ContextRepository(store.db).range_completeness(context.network_id, args.start_block, args.end_block)
                result["coverage"] = coverage
                result["workflow_status"] = "success" if coverage["state"] == "complete" else "incomplete_coverage"
            else:
                result["coverage"] = {"state": "unknown", "reason": "PostgreSQL range provenance is unavailable for this store"}
                result["workflow_status"] = "incomplete_coverage"
        print(json.dumps(result, sort_keys=True))
    finally:
        store.close()


if __name__ == "__main__":
    main()
