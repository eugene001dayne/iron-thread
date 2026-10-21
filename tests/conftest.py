import pytest

import attest_routes
import localdb


@pytest.fixture(autouse=True)
def _release_db_handles():
    yield
    localdb.close_all()  # so Windows can clean up temp databases between tests
    attest_routes._signing_key.cache_clear()
    attest_routes._store_for.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch):
    """A developer's .env (loaded when `main` is imported) must never change what the tests see."""
    for name in ("IRONTHREAD_API_KEYS", "IRONTHREAD_AUTH", "ATTEST_PRIVATE_KEY", "ATTEST_RETIRED_PUBLIC_KEYS"):
        monkeypatch.delenv(name, raising=False)

@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch):
    """A developer's .env (loaded when `main` is imported) must never change what the tests see."""
    for name in ("IRONTHREAD_API_KEYS", "IRONTHREAD_AUTH", "ATTEST_PRIVATE_KEY", "ATTEST_RETIRED_PUBLIC_KEYS"):
        monkeypatch.delenv(name, raising=False)