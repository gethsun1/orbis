"""Apply pending PostgreSQL schema migrations."""

from __future__ import annotations

import os

from orbis.observer.postgres import PostgresStore


def main() -> None:
    dsn = os.environ.get("ORBIS_DATABASE_URL", "").strip()
    if not dsn:
        raise ValueError("ORBIS_DATABASE_URL must be set")
    store = PostgresStore(dsn)
    try:
        store.migrate()
        print("PostgreSQL migrations applied")
    finally:
        store.close()


if __name__ == "__main__":
    main()
