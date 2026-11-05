# M5.1.3 PostgreSQL Recovery and Verification Report

## Result

**Disposable PostgreSQL integration verification: COMPLETE.** On 6 November 2026 (Africa/Nairobi), the complete pytest suite passed against the marked disposable PostgreSQL 18.6 cluster. This is integration-test evidence only; it is not production readiness, a production migration rehearsal, or disaster-recovery certification.

## Target and safety evidence

The test helper connected through `ORBIS_TEST_DATABASE_URL` to `127.0.0.1:55432`, database `orbis_test_m5_1_4`, as non-superuser `orbis_test_migrator`. The server reported PostgreSQL 18.6 and the database comment was exactly `ORBIS_DISPOSABLE_TEST_DATABASE=1`. The existing fail-closed test guard accepted this identity. The configured runtime principals include `orbis_runtime` (and test runtime `orbis_test_runtime`); `orbis_identity_admin` and `orbis_deployment_fencer` are separate principals. The registry focused test `test_runtime_principal_has_no_ddl_or_registry_grants` passed. The migration URL and runtime URL are separate configuration identities; tests did not use `ORBIS_DATABASE_URL`.

The main cluster at port 5432 and `orbis_dev` were not targeted. No manual PostgreSQL provisioning or credential/role repair was performed during this verification. The deployment-fencing tests temporarily change `orbis_runtime` login state and the disposable database maintenance flag, then restore both in test teardown; registry tests use isolated schemas and clean them up.

## Recovery of prior blockers

The earlier attempt was blocked by two environment conditions: the disposable database was in a maintenance state, and the `orbis_identity_admin` password was missing. The disposable cluster was returned to an available state and the identity-admin credential was provisioned before this run. The test database now passes the exact marker/name/host/migration-principal guard. No guard was weakened, and no application development database was substituted.

## Test results

Exact full-suite command:

```bash
uv run --env-file .env --with pytest pytest -v -ra
```

Result: **73 passed, 21 subtests passed in 4.75s; zero skips and zero failures.** The run included PostgreSQL integration, network-registry PostgreSQL, deployment-fencing, observer, network identity, D-02 decoder, RPC, and rule infrastructure tests.

Focused command:

```bash
uv run --env-file .env --with pytest pytest -v -ra tests/test_network_registry_postgres.py tests/test_deployment_fencing.py
```

Result: **16 passed in 3.17s** (14 registry tests and 2 deployment-fencing tests). In particular, runtime privilege separation, registry concurrency and immutability, and fencing/drain behavior passed.

## Limitations

These results establish the tested behavior against one local disposable PostgreSQL cluster. They do not establish production role provisioning, high availability, backup restoration, migration safety against production data, or disaster recovery. Keep production operational acceptance separate.
