# ORBIS environment audit

**Audited:** 3 November 2026 (Africa/Nairobi)  
**Workspace:** `/home/farmers-boy/Documents/GKM/ORBIS`

## Findings

| Area | Finding |
|---|---|
| Operating system | Ubuntu 26.04.1 LTS (Resolute Raccoon), Linux kernel 7.0.0-42-generic |
| Architecture / CPU | x86_64; AMD Athlon Gold 3150U, 2 cores / 4 threads |
| Memory | 20 GiB RAM; 12 GiB available at audit; 8 GiB swap |
| Disk | Workspace filesystem: 233 GiB total, 145 GiB available (35% used) |
| JavaScript | Node.js v24.22.0, npm 12.2.0, pnpm 12.11.2, Bun 1.4.4 |
| Python | Python 3.14.4, pip 25.1; `uv` available |
| Git | 2.53.0 |
| Containers | Docker and Docker Compose not installed |
| PostgreSQL | `psql`, `postgres`, `initdb`, and `pg_ctl` not found |
| Redis | `redis-server` and `redis-cli` not found |
| Repository | Current directory is not a Git repository; no project files other than the supplied PDF in `docs/` were present at inspection |
| Ports | Listener snapshot: local DNS on 127.0.0.53/54:53, local service on 127.0.0.1:41757, CUPS on 631; no common web/API or database port observed |

## Practical stack recommendation

Use a **Python modular monolith** for API, ingestion, persistence services and deterministic analysis: FastAPI, Pydantic, SQLAlchemy/Alembic, PostgreSQL, and `web3.py` behind a chain-provider interface. Use pytest for unit and integration tests and Ruff for lint/format. A small TypeScript package can follow once the REST contract stabilizes; Next.js dashboard and the official MCP SDK should follow their roadmap gates. Keep AI and MeTTa behind optional adapters; neither should be required for deterministic assessments.

This follows the PRD's stated preference and limits duplicated domain logic for a solo builder. The machine has sufficient memory and disk for a modest local database and services, but only two CPU cores; avoid Kubernetes and heavyweight local models. Docker, PostgreSQL and Redis are absent, so do not assume Compose-based startup works today. For initial development, use a provisioned PostgreSQL instance or install project-local/container tooling only after the owner chooses that setup. Redis/queue infrastructure should be added only when a demonstrated asynchronous workload needs it; a durable database-backed job/checkpoint approach may be enough for the first observer.

The installed Python 3.14 and Node 24 versions are newer than many dependency support matrices. Pin tested project runtimes after checking upstream compatibility; do not silently downgrade system runtimes. No packages were installed and no system configuration was changed during this audit.

## Constraints and follow-up

- Confirm a supported Python runtime for the selected FastAPI, web3.py, database and MCP dependencies before pinning.
- Select a repeatable PostgreSQL development path before M1/M2 (managed service, user-approved local installation, or Docker installation).
- Confirm RPC provider limits and canonical Whitechain testnet settings with DevRel and a live `eth_chainId` check before accepting live ingestion. A follow-up check on 3 Nov 2026 got HTTP 403 from both published candidate RPC URLs; this audit cannot verify either chain ID.
- Check port availability again when choosing local service ports.
- This is a point-in-time audit; available resources and installed tools may change.

## M2 local PostgreSQL follow-up — 3 November 2026

- Installed Ubuntu PostgreSQL server/client packages from the configured Ubuntu repository; installed PostgreSQL **18.6**.
- The `18/main` cluster is enabled and active. The observed listener is `127.0.0.1:5432`; no Docker was installed and no firewall or remote-listener changes were made.
- Created `orbis_dev` and `orbis_test` with the dedicated `orbis_app` owner role. Catalog inspection confirmed the login role is not a superuser. Credentials live only in ignored `.env`.
- Project-local psycopg 3.3.6 with binary libpq 18 is installed through `uv sync --locked`.
- PostgreSQL migration, integration, and bounded Whitechain verification results are recorded in [M2 verification report](M2_VERIFICATION_REPORT.md).
