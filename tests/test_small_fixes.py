import sqlite3

import pytest
from fastapi.testclient import TestClient

from localdb import LocalClient, LocalResponse, StorageBusy


def test_an_empty_patch_is_a_400_not_a_sql_syntax_error(tmp_path):
    db = LocalClient(str(tmp_path / "t.db"))
    db.post("/schemas", json={"id": "s", "name": "A", "created_at": "x"})
    assert db.patch("/schemas", params={"id": "eq.s"}, json={}).status_code == 400
    assert db.patch("/schemas", params={"id": "eq.s"}, json=None).status_code == 400


def test_a_locked_database_becomes_storage_busy_and_the_connection_recovers(tmp_path):
    db = LocalClient(str(tmp_path / "t.db"))

    def locked():
        raise sqlite3.OperationalError("database is locked")

    with pytest.raises(StorageBusy):
        db._guard(locked)
    assert db.post("/schemas", json={"id": "s", "name": "A", "created_at": "x"}).status_code == 201


def test_other_operational_errors_are_not_disguised_as_busy(tmp_path):
    db = LocalClient(str(tmp_path / "t.db"))

    def broken():
        raise sqlite3.OperationalError("disk I/O error")

    with pytest.raises(sqlite3.OperationalError):
        db._guard(broken)


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("IRONTHREAD_DB", str(tmp_path / "f.db"))
    monkeypatch.setenv("ATTEST_KEY_FILE", str(tmp_path / "f.key"))
    monkeypatch.delenv("IRONTHREAD_API_KEYS", raising=False)
    monkeypatch.delenv("IRONTHREAD_AUTH", raising=False)
    import main
    monkeypatch.setattr(main, "SUPABASE_URL", None)
    monkeypatch.setattr(main, "SUPABASE_KEY", None)
    return TestClient(main.app, base_url="http://localhost", client=("127.0.0.1", 50000))


def test_a_busy_database_is_a_503_with_retry_after(app_client, monkeypatch):
    import main

    class Busy(LocalClient):
        def get(self, *args, **kwargs):
            raise StorageBusy("database is locked")

    monkeypatch.setattr(main, "get_client", lambda: Busy())
    r = app_client.get("/schemas")
    assert r.status_code == 503 and r.headers["retry-after"] == "1"
    assert "busy" in r.json()["detail"]


def test_a_run_that_could_not_be_stored_is_an_error_and_gets_no_proof(app_client, monkeypatch):
    import main
    from attest_routes import get_ctx

    sid = app_client.post("/schemas", json={"name": "s", "schema_definition": {"type": "object"}}).json()["id"]

    class DiskFull(LocalClient):
        def post(self, path, json=None, params=None):
            if path.strip("/") == "validation_runs":
                return LocalResponse(500, {"message": "disk full"})
            return super().post(path, json=json, params=params)

    monkeypatch.setattr(main, "get_client", lambda: DiskFull())
    r = app_client.post("/validate", json={"schema_id": sid, "ai_output": "{}"})
    assert r.status_code == 500 and "could not be stored" in r.json()["detail"]
    assert get_ctx()["store"].chain(sid) == []   # no run, so no proof of one
