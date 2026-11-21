"""Shared pytest fixtures.

Database tests run against a real Postgres, never a mock: the schema comes from the
same migrations production applies. Where the database comes from, in order:

1. DATABASE_URL, if set and reachable (CI points this at a service container; locally use a Docker
   container). Its database name must contain "test", because every test drops and rebuilds the schema.
2. An embedded server from the optional `pgserver` package (`pip install -e ".[embedded-db]"`).
3. Otherwise DB tests are skipped - unless REQUIRE_DB=1 (set in CI), which turns
   "no database" into a failure so a misconfigured pipeline can't pass silently.
"""

from __future__ import annotations

import os
import tempfile

import psycopg
import pytest
from psycopg.rows import dict_row

from cognipm.db.migrate import apply_migrations
from tests.db_safety import is_safe_for_tests, refusal


def _reachable(url: str) -> bool:
    try:
        psycopg.connect(url, connect_timeout=3).close()
    except psycopg.Error:
        return False
    return True


@pytest.fixture(scope="session")
def database_url():
    url = os.environ.get("DATABASE_URL")
    if url and not is_safe_for_tests(url):
        pytest.fail(refusal(url))  # never fall back quietly: the point is to tell the person
    if url and _reachable(url):
        yield url
        return

    try:
        import pgserver
    except ImportError:
        pgserver = None
    if pgserver is not None:
        with tempfile.TemporaryDirectory() as data_dir:
            server = pgserver.get_server(data_dir, cleanup_mode="stop")
            try:
                yield server.get_uri()
            finally:
                server.cleanup()
        return

    message = 'no Postgres available: set DATABASE_URL or pip install -e ".[embedded-db]"'
    if os.environ.get("REQUIRE_DB") == "1":
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture
def conn(database_url, monkeypatch):
    """A fresh schema built by the real migrations, one per test. audit_log rejects
    TRUNCATE by design, so isolation is DROP SCHEMA rather than cleanup."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    connection = psycopg.connect(database_url, row_factory=dict_row, autocommit=True)
    connection.execute("DROP SCHEMA public CASCADE")
    connection.execute("CREATE SCHEMA public")
    connection.autocommit = False
    apply_migrations(connection)
    yield connection
    connection.close()
