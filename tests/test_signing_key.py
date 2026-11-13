import base64
import json

import pytest
from fastapi.testclient import TestClient

from attest_keys import KeyProblem, load_or_create_private_key, signing_key_status
from attestation import generate_keypair, key_id


def good_key():
    return generate_keypair()[0]


# ---- loading: a damaged key is refused with a reason, and never overwritten -------------------------

@pytest.mark.parametrize("content, code", [
    ("", "empty"),
    ("\n  \n", "empty"),
    ("this is not base64 at all!!", "wrong_format"),
    (base64.b64encode(b"far too short").decode() + "\n", "wrong_size"),
    (good_key() + "\nsome extra text pasted by accident\n", "multiple_lines"),
])
def test_a_damaged_key_file_is_refused_with_a_clear_reason_and_left_untouched(tmp_path, content, code):
    p = tmp_path / "k.key"
    p.write_text(content, encoding="utf-8")
    with pytest.raises(KeyProblem) as caught:
        load_or_create_private_key(p)
    assert caught.value.code == code
    assert "backup" in str(caught.value) and "never overwrites" in str(caught.value)
    assert p.read_text(encoding="utf-8") == content          # we never "fix" it by replacing it


def test_a_good_key_file_loads_and_a_missing_one_is_created(tmp_path):
    key = good_key()
    p = tmp_path / "k.key"
    p.write_text(key + "\n", encoding="utf-8")
    assert load_or_create_private_key(p) == key
    fresh = tmp_path / "new.key"
    created = load_or_create_private_key(fresh)
    assert fresh.read_text(encoding="utf-8").strip() == created


def test_a_byte_order_mark_from_notepad_is_tolerated(tmp_path):
    key = good_key()
    p = tmp_path / "k.key"
    p.write_bytes(b"\xef\xbb\xbf" + key.encode() + b"\r\n")
    assert load_or_create_private_key(p) == key


def test_the_environment_variable_is_checked_too(monkeypatch, tmp_path):
    monkeypatch.setenv("ATTEST_PRIVATE_KEY", "nonsense")
    with pytest.raises(KeyProblem) as caught:
        load_or_create_private_key(tmp_path / "unused.key")
    assert "ATTEST_PRIVATE_KEY" in str(caught.value)


# ---- the non-creating health check ------------------------------------------------------------------

def test_status_reports_each_situation_and_never_creates_the_key(tmp_path):
    p = tmp_path / "k.key"
    assert signing_key_status(p) == {"status": "will_be_created"}
    assert not p.exists()
    key, pub = generate_keypair()
    p.write_text(key + "\n", encoding="utf-8")
    assert signing_key_status(p) == {"status": "ok", "key_id": key_id(pub)}
    p.write_text("garbage\nmore\n", encoding="utf-8")
    status = signing_key_status(p)
    assert status["status"] == "error" and status["problem"] == "multiple_lines" and str(p) in status["message"]


# ---- the running server -----------------------------------------------------------------------------

@pytest.fixture
def server(tmp_path, monkeypatch):
    keyfile = tmp_path / "server.key"
    monkeypatch.setenv("IRONTHREAD_DB", str(tmp_path / "s.db"))
    monkeypatch.setenv("ATTEST_KEY_FILE", str(keyfile))
    import main
    monkeypatch.setattr(main, "SUPABASE_URL", None)
    monkeypatch.setattr(main, "SUPABASE_KEY", None)
    return TestClient(main.app, base_url="http://localhost", client=("127.0.0.1", 50000)), keyfile


def test_a_broken_key_is_explained_validation_keeps_working_and_fixing_it_needs_no_restart(server):
    client, keyfile = server
    keyfile.write_text("garbage\nmore garbage\n", encoding="utf-8")

    r = client.get("/attestations/keys")
    assert r.status_code == 503 and "unusable (multiple_lines)" in r.json()["detail"]
    assert str(keyfile) not in r.text                              # a public endpoint must not leak the path

    sid = client.post("/schemas", json={"name": "s", "schema_definition": {"type": "object"}}).json()["id"]
    run = client.post("/validate", json={"schema_id": sid, "ai_output": "{}"}).json()
    assert run["status"] == "passed" and run["attestation"] is None           # the verdict is never lost...
    assert "KeyProblem" in run["attestation_error"] and "backup" in run["attestation_error"]   # ...and says why

    health = client.get("/health").json()
    assert health["status"] == "degraded"
    assert health["signing_key"] == {"status": "error", "problem": "multiple_lines"}
    assert str(keyfile) not in json.dumps(health) and "extra text" not in json.dumps(health)

    keyfile.write_text(good_key() + "\n", encoding="utf-8")                   # fix it: no restart
    assert client.get("/attestations/keys").status_code == 200
    healthy = client.get("/health").json()
    assert healthy["status"] == "ok" and healthy["signing_key"]["status"] == "ok"
    again = client.post("/validate", json={"schema_id": sid, "ai_output": "{}"}).json()
    assert again["attestation"] is not None
    report = client.get(f"/attestations/chains/{sid}/reconcile").json()
    assert [f["problem"] for f in report["findings"]] == ["unattested_run"]   # the run made while broken is flagged


def test_health_with_no_key_yet_does_not_create_one(server):
    client, keyfile = server
    assert client.get("/health").json()["signing_key"] == {"status": "will_be_created"}
    assert not keyfile.exists()
