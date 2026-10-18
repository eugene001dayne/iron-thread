"""The offline verifier is run as a separate program, exactly as an outsider would run it."""
import copy
import json
import subprocess
import sys
from pathlib import Path

from attestation import GENESIS, generate_keypair, make_entry

SCRIPT = Path(__file__).resolve().parents[1] / "verify_offline.py"


def make_chain(priv, n=4):
    entries, prev = [], GENESIS
    for i in range(1, n + 1):
        e = make_entry(priv, chain_id="c1", seq=i, prev_hash=prev, run_id=f"r{i}", status="passed",
                       raw_input=f'{{"n": {i}}}', output={"n": i}, schema_definition={"type": "object"})
        entries.append(e)
        prev = e["entry_hash"]
    return entries


def run(tmp_path, entries, pub, *extra):
    f = tmp_path / "chain.json"
    f.write_text(json.dumps({"chain_id": "c1", "entries": entries}), encoding="utf-8")
    p = subprocess.run([sys.executable, str(SCRIPT), str(f), "--public-key", pub, *extra],
                       capture_output=True, text=True)
    return p.returncode, p.stdout


def test_intact_chain_verifies(tmp_path):
    priv, pub = generate_keypair()
    code, out = run(tmp_path, make_chain(priv), pub)
    assert code == 0 and out.startswith("VALID")


def test_altered_entry_is_rejected(tmp_path):
    priv, pub = generate_keypair()
    chain = make_chain(priv)
    chain[1]["body"]["status"] = "failed"
    code, out = run(tmp_path, chain, pub)
    assert code == 1 and "entry 2" in out and "altered" in out


def test_wrong_public_key_is_rejected(tmp_path):
    priv, _ = generate_keypair()
    _, other_pub = generate_keypair()
    code, out = run(tmp_path, make_chain(priv), other_pub)
    assert code == 1 and "different key" in out


def test_deleted_entry_is_rejected(tmp_path):
    priv, pub = generate_keypair()
    chain = make_chain(priv)
    del chain[1]
    assert run(tmp_path, chain, pub)[0] == 1


def test_truncation_is_invisible_without_a_pinned_head_but_caught_with_one(tmp_path):
    priv, pub = generate_keypair()
    chain = make_chain(priv, 4)
    head = chain[-1]["entry_hash"]            # recorded or published earlier
    truncated = chain[:3]
    assert run(tmp_path, truncated, pub)[0] == 0                          # the known limit
    code, out = run(tmp_path, truncated, pub, "--expect-head", head)      # ...closed by pinning the head
    assert code == 1 and "truncated or rewritten" in out
    assert run(tmp_path, truncated, pub, "--expect-length", "4")[0] == 1


def test_rewritten_history_by_the_key_holder_is_caught_by_a_pinned_head(tmp_path):
    priv, pub = generate_keypair()
    head = make_chain(priv, 3)[-1]["entry_hash"]
    rewritten, prev = [], GENESIS
    for i in range(1, 4):  # same key, different story, perfectly signed
        e = make_entry(priv, chain_id="c1", seq=i, prev_hash=prev, run_id=f"r{i}", status="failed",
                       raw_input="x", output=None)
        rewritten.append(e)
        prev = e["entry_hash"]
    assert run(tmp_path, rewritten, pub)[0] == 0                          # signature-valid history
    assert run(tmp_path, rewritten, pub, "--expect-head", head)[0] == 1   # but not the history we pinned


def test_the_verifier_does_not_depend_on_our_code():
    source = SCRIPT.read_text(encoding="utf-8")
    for name in ("attestation", "attest_store", "attest_keys", "localdb", "main"):
        assert f"import {name}" not in source and f"from {name}" not in source
