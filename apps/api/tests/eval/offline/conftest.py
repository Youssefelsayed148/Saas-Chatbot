"""Offline (database-free) tests for the retrieval calibration tooling.

The suite-wide autouse ``clean_tables`` fixture needs the disposable database;
these tests never touch a database, so it is overridden with a no-op here.
"""

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    yield
