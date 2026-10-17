import copy

from attestation import (
    GENESIS, canonical, sha256_hex, generate_keypair, key_id,
    make_entry, verify_entry, verify_chain,
)


def build_chain(priv, n=3):
    entries, prev = [], GENESIS
    for i in range(1, n + 1):
        e = make_entry(
            priv, chain_id="c1", seq=i, prev_hash=prev, run_id=f"run-{i}",
            status="passed", raw_input=f'{{"n": {i}}}', output={"n": i},
        )
        entries.append(e)
        prev = e["entry_hash"]
    return entries


def setup():
    priv, pub = generate_keypair()
    return priv, pub, {key_id(pub): pub}


# ── one entry ──
def test_valid_entry():
    priv, pub, _ = setup()
    assert verify_entry(build_chain(priv, 1)[0], pub) == (True, "ok")


def test_edited_body_fails():
    priv, pub, _ = setup()
    e = build_chain(priv, 1)[0]
    e["body"]["status"] = "failed"
    assert verify_entry(e, pub)[0] is False


def test_edited_and_rehashed_fails_on_signature():
    priv, pub, _ = setup()
    e = build_chain(priv, 1)[0]
    e["body"]["status"] = "failed"
    e["entry_hash"] = sha256_hex(canonical(e["body"]))
    assert verify_entry(e, pub) == (False, "signature invalid")


# ── chains ──
def test_valid_chain():
    priv, _, keys = setup()
    assert verify_chain(build_chain(priv, 3), keys) == (True, "ok")


def test_editing_middle_entry_is_caught():
    priv, _, keys = setup()
    chain = build_chain(priv, 3)
    chain[1]["body"]["status"] = "failed"
    ok, why = verify_chain(chain, keys)
    assert ok is False and "seq 2" in why


def test_deleting_middle_entry_is_caught():
    priv, _, keys = setup()
    chain = build_chain(priv, 3)
    del chain[1]
    assert verify_chain(chain, keys)[0] is False


def test_reordering_is_caught():
    priv, _, keys = setup()
    chain = build_chain(priv, 3)
    chain[0], chain[1] = chain[1], chain[0]
    assert verify_chain(chain, keys)[0] is False


# ── KNOWN LIMITS: these pass verification, and that is the point ──
def test_LIMIT_truncating_the_tail_is_invisible():
    priv, _, keys = setup()
    chain = build_chain(priv, 3)
    assert verify_chain(chain[:2], keys)[0] is True  # last entry silently dropped


def test_LIMIT_key_holder_can_rewrite_history():
    priv, _, keys = setup()
    forged, prev = [], GENESIS
    for i in range(1, 4):  # same key, different story
        e = make_entry(priv, chain_id="c1", seq=i, prev_hash=prev, run_id=f"run-{i}",
                       status="failed", raw_input="x", output=None)
        forged.append(e)
        prev = e["entry_hash"]
    assert verify_chain(forged, keys)[0] is True