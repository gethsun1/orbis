"""Runtime support window for checksummed PostgreSQL migrations.

The current release supports one schema boundary. A future release may widen
the window only by explicitly listing migrations as optional and adding tests
for every supported runtime/schema pair. Unknown migrations remain incompatible.
"""

MINIMUM_SCHEMA_VERSION = "016_observer_range_provenance.sql"
MAXIMUM_SCHEMA_VERSION = "016_observer_range_provenance.sql"
OPTIONAL_COMPATIBLE_MIGRATIONS: frozenset[str] = frozenset()
RUNTIME_RELEASE = "0.1.0"
