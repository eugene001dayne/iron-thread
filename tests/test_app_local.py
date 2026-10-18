"""End-to-end: the real app, zero external services, SQLite only."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("IRONTHREAD_DB", str(tmp_path / "e2e.db"))
    monkeypatch.setenv("ATTEST_KEY_FILE", str(tmp_path / "e2e.key"))
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


SCHEMA_DEF = {"type": "object", "required": ["amount"], "properties": {"amount": {"type": "number"}}}


def test_every_validation_returns_a_verifiable_attestation(client):
    c = client
    sid = make_schema(c)
    raw_ok, raw_bad = '{"amount": 5}', '{"amount": "x"}'
    ok = c.post("/validate", json={"schema_id": sid, "ai_output": raw_ok}).json()
    bad = c.post("/validate", json={"schema_id": sid, "ai_output": raw_bad}).json()

    assert [ok["attestation"]["body"]["seq"], bad["attestation"]["body"]["seq"]] == [1, 2]
    assert ok["attestation"]["body"]["status"] == "passed"
    assert bad["attestation"]["body"]["status"] == "failed"  # failures are attested too

    r = c.post("/attestations/verify", json={
        "entry": ok["attestation"], "input": raw_ok, "output": ok["data"], "schema_definition": SCHEMA_DEF,
    }).json()
    assert r == {"valid": True, "reason": "ok", "input_matches": True,
                 "output_matches": True, "schema_matches": True}

    chain = c.get(f"/attestations/chains/{sid}/verify").json()
    assert chain["valid"] is True and chain["length"] == 2
    assert chain["head_hash"] == bad["attestation"]["entry_hash"]


def test_attestation_binds_the_exact_schema_and_input(client):
    c = client
    sid = make_schema(c)
    run = c.post("/validate", json={"schema_id": sid, "ai_output": '{"amount": 5}'}).json()
    other_schema = {**SCHEMA_DEF, "required": []}
    r = c.post("/attestations/verify", json={
        "entry": run["attestation"], "input": '{"amount": 6}', "schema_definition": other_schema}).json()
    assert r["valid"] is True and r["input_matches"] is False and r["schema_matches"] is False


def test_tampered_attestation_is_rejected(client):
    c = client
    sid = make_schema(c)
    run = c.post("/validate", json={"schema_id": sid, "ai_output": '{"amount": "x"}'}).json()
    forged = run["attestation"]
    forged["body"]["status"] = "passed"
    assert c.post("/attestations/verify", json={"entry": forged}).json()["valid"] is False


def test_signing_failure_never_loses_the_validation(client, monkeypatch):
    import main

    def boom():
        raise RuntimeError("key store offline")

    monkeypatch.setattr(main, "attest_ctx", boom)
    c = client
    sid = make_schema(c)
    run = c.post("/validate", json={"schema_id": sid, "ai_output": '{"amount": 5}'}).json()
    assert run["status"] == "passed"                       # the validation still happened
    assert run["attestation"] is None                      # and the missing proof is visible, not hidden
    assert "key store offline" in run["attestation_error"]
    assert len(c.get("/runs").json()) == 1                 # and the run was stored


def test_an_invalid_json_schema_is_rejected_when_created(client):
    r = client.post("/schemas", json={"name": "bad", "schema_definition": {"type": "strng"}})
    assert r.status_code == 400 and "Invalid JSON Schema" in r.json()["detail"]
    assert client.get("/schemas").json() == []


def test_standard_json_schema_features_work_end_to_end(client):
    c = client
    sid = c.post("/schemas", json={"name": "order", "schema_definition": {
        "type": "object", "required": ["items"], "additionalProperties": False,
        "properties": {"items": {"type": "array", "items": {
            "type": "object", "required": ["price"],
            "properties": {"price": {"type": "number", "minimum": 0}}}}}}}).json()["id"]
    good = c.post("/validate", json={"schema_id": sid, "ai_output": '{"items": [{"price": 5}]}'}).json()
    bad = c.post("/validate", json={
        "schema_id": sid, "ai_output": '{"items": [{"price": -1}, {}], "extra": 1}'}).json()
    assert good["status"] == "passed"
    assert bad["status"] == "failed"
    assert "items[0].price" in bad["reason"] and "items[1]" in bad["reason"]
    assert bad["attestation"]["body"]["status"] == "failed"   # a rejected verdict is attested too
