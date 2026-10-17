"""End-to-end: the real app, zero external services, SQLite only."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("IRONTHREAD_DB", str(tmp_path / "e2e.db"))
    import main
    monkeypatch.setattr(main, "SUPABASE_URL", None)  # never touch a real Supabase from tests
    monkeypatch.setattr(main, "SUPABASE_KEY", None)
    return TestClient(main.app)


def make_schema(c):
    r = c.post("/schemas", json={"name": "invoice", "schema_definition": {
        "type": "object", "required": ["amount"], "properties": {"amount": {"type": "number"}}}})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_full_flow_without_any_service(client):
    c = client
    sid = make_schema(c)
    assert c.get("/schemas").json()[0]["id"] == sid

    ok = c.post("/validate", json={"schema_id": sid, "ai_output": '{"amount": 5}'}).json()
    bad = c.post("/validate", json={"schema_id": sid, "ai_output": '{"amount": "x"}'}).json()
    assert ok["status"] == "passed" and bad["status"] == "failed"

    runs = c.get("/runs").json()
    assert len(runs) == 2 and runs[0]["id"] == bad["run_id"]  # newest first
    assert c.get("/health").status_code == 200


def test_existing_hash_chain_still_verifies(client):
    c = client
    sid = make_schema(c)
    ids = [c.post("/validate", json={"schema_id": sid, "ai_output": f'{{"amount": {i}}}'}).json()["run_id"]
           for i in range(3)]
    assert c.get(f"/runs/{ids[1]}/verify").status_code == 200
    assert c.get(f"/schemas/{sid}/chain").status_code == 200


def test_dashboard_analytics_and_webhooks(client):
    c = client
    sid = make_schema(c)
    c.post("/validate", json={"schema_id": sid, "ai_output": '{"amount": 1}'})
    for path in ["/dashboard/stats", "/analytics/errors", "/analytics/trends",
                 "/analytics/models", "/analytics/schemas", "/runs/export"]:
        assert c.get(path).status_code == 200, path

    w = c.post("/webhooks", json={"name": "n", "url": "http://localhost:9/x"}).json()
    assert len(c.get("/webhooks").json()) == 1
    c.delete(f"/webhooks/{w['id']}")
    assert c.get("/webhooks").json()[0]["active"] is False
