from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from auth import cors_settings, is_local, new_key

KEY = "it_test_" + "a" * 32
OTHER = "it_other_" + "b" * 32


def req(host="localhost:8000", ip="127.0.0.1", **headers):
    return SimpleNamespace(client=SimpleNamespace(host=ip) if ip else None,
                           headers={"host": host, **{k.replace("_", "-"): v for k, v in headers.items()}})


# ---- the "is this really local?" decision -------------------------------------------------------

@pytest.mark.parametrize("r", [
    req(), req("127.0.0.1:8000"), req("[::1]:8000", "::1"), req("localhost", "::ffff:127.0.0.1"), req(ip=None),
])
def test_genuinely_local_requests(r):
    assert is_local(r) is True


@pytest.mark.parametrize("r", [
    req(ip="203.0.113.9"),                            # a remote machine
    req(host="evil.example:8000"),                    # DNS rebinding: loopback address, foreign hostname
    req(x_forwarded_for="203.0.113.9"),               # reverse proxy in front: loopback proves nothing
    req(forwarded="for=203.0.113.9"),
    req(x_real_ip="203.0.113.9"),
    req(host=""),
    req(ip="not-an-ip"),
])
def test_requests_that_are_not_provably_local(r):
    assert is_local(r) is False


# ---- the running app ----------------------------------------------------------------------------

@pytest.fixture
def make(tmp_path, monkeypatch):
    monkeypatch.setenv("IRONTHREAD_DB", str(tmp_path / "a.db"))
    monkeypatch.setenv("ATTEST_KEY_FILE", str(tmp_path / "a.key"))
    monkeypatch.delenv("IRONTHREAD_API_KEYS", raising=False)
    monkeypatch.delenv("IRONTHREAD_AUTH", raising=False)
    import main
    monkeypatch.setattr(main, "SUPABASE_URL", None)
    monkeypatch.setattr(main, "SUPABASE_KEY", None)

    def build(host="localhost", ip="127.0.0.1"):
        return TestClient(main.app, base_url=f"http://{host}", client=(ip, 50000))
    return build


def test_no_key_configured_works_from_localhost(make):
    assert make().get("/schemas").status_code == 200


def test_no_key_configured_refuses_everyone_else_with_instructions(make):
    r = make(ip="203.0.113.9").get("/schemas")
    assert r.status_code == 403 and "IRONTHREAD_API_KEYS" in r.json()["detail"]
    assert make(host="evil.example").get("/schemas").status_code == 403            # DNS rebinding
    assert make().get("/schemas", headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 403


def test_public_endpoints_stay_public(make):
    remote = make(ip="203.0.113.9")
    assert remote.get("/health").status_code == 200
    assert remote.get("/attestations/keys").status_code == 200
    assert remote.post("/attestations/verify", json={"entry": {}}).status_code == 200


def test_explicitly_open_mode(make, monkeypatch):
    monkeypatch.setenv("IRONTHREAD_AUTH", "off")
    assert make(ip="203.0.113.9").get("/schemas").status_code == 200


def test_with_keys_a_key_is_required_even_from_localhost(make, monkeypatch):
    monkeypatch.setenv("IRONTHREAD_API_KEYS", KEY)
    c = make()
    r = c.get("/schemas")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert c.get("/schemas", headers={"Authorization": "Bearer " + OTHER}).status_code == 401
    assert c.get("/schemas", headers={"X-API-Key": "short"}).status_code == 401
    assert c.get("/schemas", headers={"Authorization": "Bearer " + KEY}).status_code == 200
    assert c.get("/schemas", headers={"X-API-Key": KEY}).status_code == 200


def test_a_valid_key_works_from_anywhere_and_rotation_keeps_both_keys_valid(make, monkeypatch):
    monkeypatch.setenv("IRONTHREAD_API_KEYS", f"{KEY}, {OTHER}")
    remote = make(host="api.example.com", ip="203.0.113.9")
    assert remote.get("/schemas", headers={"X-API-Key": KEY}).status_code == 200
    assert remote.get("/schemas", headers={"X-API-Key": OTHER}).status_code == 200
    assert remote.get("/schemas").status_code == 401


def test_public_endpoints_need_no_key_even_when_keys_are_set(make, monkeypatch):
    monkeypatch.setenv("IRONTHREAD_API_KEYS", KEY)
    c = make(ip="203.0.113.9")
    assert c.get("/health").status_code == 200 and c.get("/attestations/keys").status_code == 200


def test_every_data_endpoint_is_protected(make, monkeypatch):
    monkeypatch.setenv("IRONTHREAD_API_KEYS", KEY)
    c = make()
    for method, path in [("get", "/schemas"), ("post", "/schemas"), ("post", "/validate"), ("get", "/runs"),
                         ("get", "/runs/export"), ("get", "/webhooks"), ("get", "/dashboard/stats"),
                         ("get", "/analytics/errors"), ("get", "/attestations/runs/x"),
                         ("get", "/attestations/chains/x"), ("get", "/attestations/chains/x/verify"),
                         ("get", "/attestations/chains/x/reconcile")]:
        assert getattr(c, method)(path).status_code == 401, f"{method.upper()} {path} is open!"


def test_a_weak_key_is_refused_loudly_not_accepted_silently(make, monkeypatch):
    monkeypatch.setenv("IRONTHREAD_API_KEYS", "password")
    r = make().get("/schemas", headers={"X-API-Key": "password"})
    assert r.status_code == 500 and "shorter than 16" in r.json()["detail"]


def test_the_whole_flow_works_with_a_key(make, monkeypatch):
    monkeypatch.setenv("IRONTHREAD_API_KEYS", KEY)
    c, h = make(), {"Authorization": "Bearer " + KEY}
    sid = c.post("/schemas", headers=h, json={"name": "s", "schema_definition": {"type": "object"}}).json()["id"]
    run = c.post("/validate", headers=h, json={"schema_id": sid, "ai_output": "{}"}).json()
    assert run["attestation"] is not None
    assert c.get(f"/attestations/chains/{sid}/reconcile", headers=h).json()["ok"] is True


# ---- browsers ------------------------------------------------------------------------------------

def test_other_websites_cannot_read_a_local_server_from_the_browser(make):
    c = make()
    evil = c.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in evil.headers
    fine = c.get("/health", headers={"Origin": "http://localhost:3000"})
    assert fine.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_settings_can_be_configured_explicitly(monkeypatch):
    monkeypatch.setenv("IRONTHREAD_CORS_ORIGINS", "https://a.example, https://b.example")
    assert cors_settings()["allow_origins"] == ["https://a.example", "https://b.example"]
    monkeypatch.setenv("IRONTHREAD_CORS_ORIGINS", "*")
    assert cors_settings()["allow_origins"] == ["*"] and cors_settings()["allow_credentials"] is False


def test_generated_keys_are_long_and_unique():
    a, b = new_key(), new_key()
    assert a != b and len(a) >= 40 and a.startswith("it_")
