"""P1-02: the disposable-database guard refuses non-``_test`` database names."""

import pytest

from tests.conftest import disposable_url


def test_guard_accepts_test_suffix() -> None:
    url = disposable_url("postgresql://u:p@localhost:55432/chatbot_dev", "chatbot_dev_test")
    assert url.endswith("/chatbot_dev_test")


def test_guard_accepts_preexisting_test_db_name() -> None:
    url = disposable_url(
        "postgresql://u:p@localhost:55432/chatbot_dev", "chatbot_dev_migration_test"
    )
    assert url.endswith("/chatbot_dev_migration_test")


def test_guard_accepts_explicit_slice_test_database() -> None:
    url = disposable_url("postgresql://u:p@localhost:55462/saas-test-db", "saas-test-db")
    assert url.endswith("/saas-test-db")


@pytest.mark.parametrize("bad_name", ["chatbot_dev", "chatbot_dev_test_copy", "main"])
def test_guard_refuses_non_test_names(bad_name: str) -> None:
    with pytest.raises(RuntimeError, match="non-disposable"):
        disposable_url("postgresql://u:p@localhost:55432/chatbot_dev", bad_name)
