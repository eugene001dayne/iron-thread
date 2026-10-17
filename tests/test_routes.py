import copy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from attestation import generate_keypair
from attest_keys import trusted_public_keys
from attest_routes import get_ctx, router
from attest_store import SqliteStore, record_attestation

RAW = '{"amount": 120}'
OUT = {"amount": 120}


@pytest.fixture
def client(tmp_path):
    priv, _ = generate_keypair()
    store = SqliteStore(str(tmp_path / "t.db"))
    for i in range(1, 4):
        record_attestation(store, priv, chain_id="inv", run_id=f"r{i}", status="passed",
                           raw_input=RAW if i == 2 else f'{{"n": {i}}}', output=OUT if i == 2 else {"n": i})
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ctx] = lambda: {"store": store, "priv": priv, "keys": trusted_public_keys(priv)}
    return TestClient(app), store


def test_keys_are_published(client):
    c, _ = client
    r = c.get("/attestations/keys").json()
    assert r["algorithm"] == "Ed25519" and len(r["keys"]) == 1


def test_fetch_attestation_by_run(client):
    c, _ = client
    assert c.get("/attestations/runs/r2").json()["body"]["seq"] == 2
    assert c.get("/attestations/runs/nope").status_code == 404


def test_chain_verify_endpoint(client):
    c, store = client
    r = c.get("/attestations/chains/inv/verify").json()
    assert r["valid"] is True and r["length"] == 3
    assert r["head_hash"] == store.last("inv")["entry_hash"]
    assert c.get("/attestations/chains/zzz/verify").status_code == 404


def test_post_verify_genuine_entry_and_data(client):
    c, _ = client
    entry = c.get("/attestations/runs/r2").json()
    r = c.post("/attestations/verify", json={"entry": entry, "input": RAW, "output": OUT}).json()
    assert r == {"valid": True, "reason": "ok", "input_matches": True, "output_matches": True}


def test_post_verify_detects_wrong_data(client):
    c, _ = client
    entry = c.get("/attestations/runs/r2").json()
    r = c.post("/attestations/verify", json={"entry": entry, "input": '{"amount": 999}'}).json()
    assert r["valid"] is True and r["input_matches"] is False


def test_post_verify_detects_forged_entry(client):
    c, _ = client
    entry = c.get("/attestations/runs/r2").json()
    forged = copy.deepcopy(entry)
    forged["body"]["status"] = "failed"
    assert c.post("/attestations/verify", json={"entry": forged}).json()["valid"] is False


def test_post_verify_junk_does_not_crash(client):
    c, _ = client
    assert c.post("/attestations/verify", json={"entry": {}}).json()["valid"] is False
