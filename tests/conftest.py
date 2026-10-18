import pytest

import localdb


@pytest.fixture(autouse=True)
def _release_db_handles():
    yield
    localdb.close_all()  # so Windows can clean up temp databases between tests
