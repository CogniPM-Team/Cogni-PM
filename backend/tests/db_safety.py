"""The database tests rebuild their schema from scratch for every test (DROP SCHEMA ... CASCADE), so pointing
them at a database that holds real data would erase it. This is the check that stops that."""

from __future__ import annotations

from urllib.parse import urlparse


def database_name(url: str) -> str:
    return urlparse(url).path.lstrip("/")


def is_safe_for_tests(url: str) -> bool:
    """Only a database whose name contains "test" may be wiped by the test suite."""
    return "test" in database_name(url).lower()


def refusal(url: str) -> str:
    return (
        f"Refusing to run the tests against database {database_name(url)!r}: they drop the schema for every test, "
        "which would erase its data. Point DATABASE_URL at a separate database whose name contains 'test', for "
        "example postgresql://cognipm:cognipm@localhost:5432/cognipm_test (see README.md, 'Run the tests')."
    )
