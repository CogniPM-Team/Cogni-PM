"""The tests wipe their database, so they must refuse any database that is not clearly a test one."""

from __future__ import annotations

import pytest

from tests.db_safety import database_name, is_safe_for_tests, refusal


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://cognipm:cognipm@localhost:5432/cognipm_test",
        "postgresql://u:p@db.internal:5433/Test_DB?sslmode=require",
        "postgresql://u:p@localhost/ci-test",
    ],
)
def test_a_database_with_test_in_its_name_may_be_wiped(url):
    assert is_safe_for_tests(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://cognipm:cognipm@localhost:5432/cognipm",
        "postgresql://u:p@prod.example.com/orders",
        "postgresql://u:p@localhost:5432/postgres",
        "postgresql://u:p@localhost:5432/",
    ],
)
def test_any_other_database_is_refused_and_the_message_says_what_to_do(url):
    assert not is_safe_for_tests(url)
    message = refusal(url)
    assert database_name(url) in message and "'test'" in message and "README.md" in message
