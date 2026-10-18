import pytest

import attest_routes
import localdb


@pytest.fixture(autouse=True)
def _release_db_handles():
    yield
    localdb.close_all()  # so Windows can clean up temp databases between tests
    attest_routes._signing_key.cache_clear()
    attest_routes._store_for.cache_clear()
