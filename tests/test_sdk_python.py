import copy
import json
import re
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk"))

import ironthread  # noqa: E402
import verify_offline  # noqa: E402  (the standalone script in the repo root)
from attestation import GENESIS, generate_keypair, make_entry  # noqa: E402
from ironthread import IronThread, IronThreadError, verify_chain  # noqa: E402

SCHEMA = {"type": "object", "required": ["amount"], "properties": {"amount": {"type": "number"}}}


def _server(tmp_path, monkeypatch, keys=None):
    monkeypatch.setenv("IRONTHREAD_DB", str(tmp_path / "s.db"))
    monkeypatch.setenv("ATTEST_KEY_FILE", str(tmp_path / "s.key"))
    monkeypatch.delenv("IRONTHREAD_API_KEY", raising=False)
    monkeypatch.delenv("IRONTHREAD_URL", raising=False)
    if keys:
        monkeypatch.setenv("IRONTHREAD_API_KEYS", keys)
    import main
    monkeypatch.setattr(main, "SUPABASE_URL", None)
    monkeypatch.setattr(main, "SUPABASE_KEY", None)
    return main


@pytest.fixture
def it(tmp_path, monkeypatch):
    main = _server(tmp_path, monkeypatch)
    http = TestClient(main.app, base_url="http://localhost", client=("127.0.0.1", 50000))
    return IronThread(client=http)


def test_the_whole_round_trip_against_the_real_server(it):
    schema = it.create_schema("invoice", SCHEMA)
    good = it.validate({"amount": 120}, schema["id"])            # a dict is serialised for you
    bad = it.validate('{"amount": "about 120"}', schema["id"])
    assert good.passed and not bad.passed
    assert good.attestation["body"]["status"] == "passed" and bad.attestation["body"]["status"] == "failed"
    assert good.attestation_error is None

    checked = it.verify_attestation(good.attestation, input=json.dumps({"amount": 120}),
                                    output=good.data, schema_definition=SCHEMA)
    assert checked == {"valid": True, "reason": "ok", "input_matches": True,
                       "output_matches": True, "schema_matches": True}
    assert it.get_attestation(good.run_id)["entry_hash"] == good.attestation["entry_hash"]

    public_key = it.public_keys()[0]["public_key"]
    chain = it.get_chain(schema["id"])
    assert len(chain) == 2 and chain[-1]["entry_hash"] == bad.attestation["entry_hash"]

    result = it.verify_chain_offline(schema["id"], public_key, expect_head=chain[-1]["entry_hash"],
                                     expect_length=2)
    assert result and result.message.startswith("OK: 2 entries")
    assert it.verify_chain_remote(schema["id"])["valid"] is True
    assert it.reconcile(schema["id"])["ok"] is True

    forged = copy.deepcopy(chain)
    forged[0]["body"]["status"] = "failed"
    assert not verify_chain(forged, public_key)
    assert not verify_chain(chain[:1], public_key, expect_head=chain[-1]["entry_hash"])   # truncation


def test_batch_validation_serialises_objects_too(it):
    schema = it.create_schema("invoice", SCHEMA)
    batch = it.validate_batch([{"amount": 1}, '{"amount": "x"}'], schema["id"])
    assert (batch.total, batch.passed, batch.failed) == (2, 1, 1)
    assert batch.results[0].attestation is not None


def test_server_errors_carry_the_servers_explanation_and_stay_httpx_compatible(it):
    with pytest.raises(IronThreadError) as caught:
        it.get_attestation("no-such-run")
    error = caught.value
    assert isinstance(error, httpx.HTTPStatusError)               # old `except` clauses keep working
    assert error.status_code == 404 and error.detail == "No attestation for this run"
    assert "404" in str(error) and "No attestation for this run" in str(error)


def test_a_server_that_needs_a_key_says_so(tmp_path, monkeypatch):
    main = _server(tmp_path, monkeypatch, keys="it_test_" + "k" * 30)
    http = TestClient(main.app, base_url="http://localhost", client=("127.0.0.1", 50000))
    with pytest.raises(IronThreadError) as caught:
        IronThread(client=http).list_schemas()
    assert caught.value.status_code == 401 and "API key" in caught.value.detail
    authed = TestClient(main.app, base_url="http://localhost", client=("127.0.0.1", 50000),
                        headers={"Authorization": "Bearer it_test_" + "k" * 30})
    assert IronThread(client=authed).list_schemas() == []


def test_api_key_and_url_come_from_arguments_or_the_environment(monkeypatch):
    monkeypatch.delenv("IRONTHREAD_API_KEY", raising=False)
    monkeypatch.delenv("IRONTHREAD_URL", raising=False)
    assert IronThread().base_url == "http://localhost:8000"
    assert "authorization" not in IronThread()._client.headers
    monkeypatch.setenv("IRONTHREAD_URL", "http://example.test:9000/")
    monkeypatch.setenv("IRONTHREAD_API_KEY", "from-env-key")
    from_env = IronThread()
    assert from_env.base_url == "http://example.test:9000"
    assert from_env._client.headers["authorization"] == "Bearer from-env-key"
    explicit = IronThread("http://other.test", api_key="explicit-key")
    assert explicit.base_url == "http://other.test"
    assert explicit._client.headers["authorization"] == "Bearer explicit-key"


def test_no_server_gives_a_friendly_connection_error():
    with pytest.raises(httpx.ConnectError) as caught:
        IronThread("http://127.0.0.1:9", timeout=3).health()
    assert "Cannot reach Iron-Thread" in str(caught.value) and "python -m uvicorn main:app" in str(caught.value)


def _chain(n=4):
    priv, pub = generate_keypair()
    entries, prev = [], GENESIS
    for i in range(1, n + 1):
        e = make_entry(priv, chain_id="c", seq=i, prev_hash=prev, run_id=f"r{i}", status="passed",
                       raw_input="{}", output={"i": i}, schema_definition={"type": "object"})
        entries.append(e)
        prev = e["entry_hash"]
    return entries, pub


def test_the_sdk_verifier_agrees_with_the_standalone_verifier_on_every_kind_of_damage():
    entries, pub = _chain()
    other_pub = generate_keypair()[1]
    altered = copy.deepcopy(entries)
    altered[1]["body"]["status"] = "failed"
    resigned_badly = copy.deepcopy(entries)
    resigned_badly[2]["signature"] = resigned_badly[1]["signature"]
    reordered = [entries[1], entries[0], *entries[2:]]
    malformed = copy.deepcopy(entries)
    del malformed[0]["signature"]
    cases = [
        (entries, pub, {}),
        (entries, other_pub, {}),
        (altered, pub, {}),
        (resigned_badly, pub, {}),
        (reordered, pub, {}),
        (entries[:2], pub, {}),
        (entries[1:], pub, {}),
        (entries[:3], pub, {"expect_head": entries[-1]["entry_hash"]}),
        (entries, pub, {"expect_length": 9}),
        (malformed, pub, {}),
        ([], pub, {}),
        (entries, "not-a-key", {}),
    ]
    for chain, key, kwargs in cases:
        sdk = verify_chain(chain, key, **kwargs)
        standalone = verify_offline.verify(chain, key, kwargs.get("expect_head"), kwargs.get("expect_length"))
        assert (sdk.ok, sdk.message) == standalone, kwargs


def test_the_package_version_is_consistent():
    pyproject = (ROOT / "sdk" / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
    assert ironthread.__version__ == declared


def test_the_sdk_ships_the_same_license_as_the_repository():
    # the Python package needs its own copy of LICENSE next to pyproject.toml; keep them identical
    assert (ROOT / "sdk" / "LICENSE").read_text(encoding="utf-8").splitlines() == \
        (ROOT / "LICENSE").read_text(encoding="utf-8").splitlines()
