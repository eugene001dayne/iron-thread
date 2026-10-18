import threading

import pytest

from attestation import GENESIS, generate_keypair, key_id, verify_chain
from attest_store import DuplicateRun, SqliteStore, record_attestation


def rec(store, priv, chain, run_id):
    return record_attestation(
        store, priv, chain_id=chain, run_id=run_id, status="passed",
        raw_input=f'{{"id": "{run_id}"}}', output={"id": run_id},
    )


def test_sequential_records_form_a_valid_chain(tmp_path):
    store = SqliteStore(str(tmp_path / "t.db"))
    priv, pub = generate_keypair()
    for i in range(5):
        rec(store, priv, "c1", f"run-{i}")
    chain = store.chain("c1")
    assert [e["body"]["seq"] for e in chain] == [1, 2, 3, 4, 5]
    assert chain[0]["body"]["prev_hash"] == GENESIS
    assert verify_chain(chain, {key_id(pub): pub}) == (True, "ok")


def test_chains_are_independent(tmp_path):
    store = SqliteStore(str(tmp_path / "t.db"))
    priv, _ = generate_keypair()
    rec(store, priv, "a", "r1")
    rec(store, priv, "b", "r2")
    assert store.last("a")["body"]["seq"] == 1
    assert store.last("b")["body"]["seq"] == 1


def test_same_run_twice_is_rejected(tmp_path):
    store = SqliteStore(str(tmp_path / "t.db"))
    priv, _ = generate_keypair()
    rec(store, priv, "c1", "run-1")
    with pytest.raises(DuplicateRun):
        rec(store, priv, "c1", "run-1")


def test_concurrent_writers_never_fork_the_chain(tmp_path):
    store = SqliteStore(str(tmp_path / "t.db"))
    priv, pub = generate_keypair()
    errors = []

    def worker(w):
        try:
            for i in range(10):
                rec(store, priv, "c1", f"w{w}-{i}")
        except Exception as e:  # noqa
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert errors == []
    chain = store.chain("c1")
    assert len(chain) == 60
    assert verify_chain(chain, {key_id(pub): pub}) == (True, "ok")


def test_by_run_lookup(tmp_path):
    store = SqliteStore(str(tmp_path / "t.db"))
    priv, _ = generate_keypair()
    e = rec(store, priv, "c1", "run-42")
    assert store.by_run("run-42")["entry_hash"] == e["entry_hash"]
    assert store.by_run("nope") is None


def test_store_uses_the_threads_durable_connection(tmp_path):
    import localdb
    p = str(tmp_path / "t.db")
    store = SqliteStore(p)
    durable = localdb._connection(p, durable=True)
    priv, _ = generate_keypair()
    rec(store, priv, "c1", "r1")
    assert localdb._connection(p, durable=True) is durable          # reused, not reopened
    assert localdb._connection(p, durable=False) is not durable     # ordinary tables use a different one
    assert durable.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL: fsync on every commit
    assert localdb._connection(p, durable=False).execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL


def test_store_still_works_after_a_rejected_duplicate(tmp_path):
    store = SqliteStore(str(tmp_path / "t.db"))
    priv, pub = generate_keypair()
    rec(store, priv, "c1", "run-1")
    with pytest.raises(DuplicateRun):
        rec(store, priv, "c1", "run-1")
    rec(store, priv, "c1", "run-2")  # the shared connection must not be stuck mid-transaction
    assert verify_chain(store.chain("c1"), {key_id(pub): pub}) == (True, "ok")
