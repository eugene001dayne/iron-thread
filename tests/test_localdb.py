import pytest

from localdb import LocalClient


@pytest.fixture
def db(tmp_path):
    return LocalClient(str(tmp_path / "t.db"))


def seed(db):
    db.post("/schemas", json={"id": "s1", "name": "A", "description": None,
                              "schema_definition": {"type": "object", "n": [1, 2]}, "created_at": "2026-01-01"})
    for i, (status, sid) in enumerate([("passed", "s1"), ("failed", "s1"), ("corrected", "s1"), ("passed", "s2")]):
        db.post("/validation_runs", json={
            "id": f"r{i}", "schema_id": sid, "raw_ai_output": "{}", "status": status,
            "validated_output": {"i": i} if status != "failed" else None,
            "attempts": 1, "latency_ms": 10 * i, "confidence_score": 0.5 + i / 10,
            "created_at": f"2026-01-0{i + 1}",
        })


def test_roundtrip_decodes_json_and_numbers(db):
    seed(db)
    s = db.get("/schemas", {"id": "eq.s1"}).json()[0]
    assert s["schema_definition"] == {"type": "object", "n": [1, 2]}
    r = db.get("/validation_runs", {"id": "eq.r2"}).json()[0]
    assert r["validated_output"] == {"i": 2} and r["latency_ms"] == 20


def test_in_eq_order_limit_select(db):
    seed(db)
    rows = db.get("/validation_runs", {
        "schema_id": "eq.s1", "status": "in.(passed,corrected)",
        "select": "id,status", "order": "created_at.desc", "limit": "5"}).json()
    assert rows == [{"id": "r2", "status": "corrected"}, {"id": "r0", "status": "passed"}]


def test_or_with_is_null(db):
    for i, sid in enumerate(["s1", None, "s2"]):
        db.post("/webhooks", json={"id": f"w{i}", "name": "n", "url": "u", "on_failure": True,
                                   "on_success": False, "schema_id": sid, "active": True, "created_at": "x"})
    rows = db.get("/webhooks", {"active": "eq.true", "or": "(schema_id.eq.s1,schema_id.is.null)"}).json()
    assert sorted(r["id"] for r in rows) == ["w0", "w1"]
    assert rows[0]["on_failure"] is True and rows[0]["on_success"] is False


def test_patch_soft_delete_hides_from_active_filter(db):
    db.post("/webhooks", json={"id": "w1", "name": "n", "url": "u", "on_failure": True,
                               "on_success": False, "schema_id": None, "active": True, "created_at": "x"})
    db.patch("/webhooks", params={"id": "eq.w1"}, json={"active": False})
    assert db.get("/webhooks", {"active": "eq.true"}).json() == []
    assert db.get("/webhooks", {"id": "eq.w1"}).json()[0]["active"] is False


def test_unknown_table_and_column_are_rejected(db):
    assert db.get("/users").status_code == 400
    assert db.get("/schemas", {"evil; DROP TABLE schemas": "eq.1"}).status_code == 400
    assert db.get("/schemas", {"select": "id,password"}).status_code == 400


def test_values_are_parameterised(db):
    seed(db)
    assert db.get("/schemas", {"id": "eq.x'; DROP TABLE schemas;--"}).json() == []
    assert len(db.get("/schemas").json()) == 1


def test_duplicate_primary_key_is_409(db):
    db.post("/schemas", json={"id": "s1", "name": "A", "created_at": "x"})
    assert db.post("/schemas", json={"id": "s1", "name": "B", "created_at": "x"}).status_code == 409


def test_tables_are_recreated_if_the_db_file_is_deleted(tmp_path):
    import os
    p = str(tmp_path / "t.db")
    import localdb
    with LocalClient(p) as c:
        c.post("/schemas", json={"id": "s1", "name": "A", "created_at": "x"})
    localdb.close_all()  # release connections, or Windows won't let us delete the file
    for f in (p, p + "-wal", p + "-shm"):
        if os.path.exists(f):
            os.remove(f)
    with LocalClient(p) as c:
        assert c.get("/schemas").json() == []


def test_failed_multi_row_insert_rolls_back_and_connection_stays_usable(db):
    r = db.post("/schemas", json=[{"id": "a", "name": "A", "created_at": "x"}, {"id": "b", "nope": 1}])
    assert r.status_code == 400
    assert db.get("/schemas").json() == []  # first row was rolled back, not left half-written
    assert db.post("/schemas", json={"id": "c", "name": "C", "created_at": "x"}).status_code == 201


def test_connection_is_reused_within_a_thread_and_not_shared_across_threads(tmp_path):
    import threading
    p = str(tmp_path / "t.db")
    seen, done = {}, threading.Event()

    def work(name):
        with LocalClient(p) as a:
            first = a._c
        with LocalClient(p) as b:
            second = b._c
        seen[name] = (first, second)  # keep references so object identity can't be recycled
        done.wait(5)

    threads = [threading.Thread(target=work, args=(n,)) for n in "xy"]
    [t.start() for t in threads]
    while len(seen) < 2:
        pass
    done.set()
    [t.join() for t in threads]
    assert seen["x"][0] is seen["x"][1]      # reused inside one thread
    assert seen["x"][0] is not seen["y"][0]  # never shared between threads


def test_exiting_the_with_block_does_not_close_the_connection(tmp_path):
    with LocalClient(str(tmp_path / "t.db")) as c:
        conn = c._c
    assert conn.execute("SELECT 1").fetchone()[0] == 1
