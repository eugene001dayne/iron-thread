"""SQLite storage for attestation chains + the one function the app will call."""
import json
import sqlite3
from contextlib import contextmanager

from attestation import GENESIS, make_entry
from localdb import _connection  # shared per-thread connections


class Conflict(Exception):
    """Another writer already took this (chain_id, seq). Safe to retry."""


class DuplicateRun(Exception):
    """This run_id already has an attestation. NOT safe to retry."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS attestations (
    chain_id   TEXT    NOT NULL,
    seq        INTEGER NOT NULL,
    run_id     TEXT    NOT NULL UNIQUE,
    entry_hash TEXT    NOT NULL,
    signature  TEXT    NOT NULL,
    key_id     TEXT    NOT NULL,
    body       TEXT    NOT NULL,
    PRIMARY KEY (chain_id, seq)
);
"""


class SqliteStore:
    def __init__(self, path="ironthread.db"):
        self.path = path
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute(SCHEMA)

    @contextmanager
    def _conn(self):
        # The calling thread's long-lived connection (reopening a WAL database on every call is what
        # made writes ~100 ms on Windows). durable=True keeps a full fsync on every commit, because
        # audit entries must survive a power cut.
        c = _connection(self.path, durable=True)
        with c:  # commit on success, roll back on error; does NOT close
            yield c

    @staticmethod
    def _entry(row):
        return {"body": json.loads(row["body"]), "entry_hash": row["entry_hash"], "signature": row["signature"]}

    def last(self, chain_id):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM attestations WHERE chain_id=? ORDER BY seq DESC LIMIT 1", (chain_id,)
            ).fetchall()  # fetchall, so no half-read statement is left holding a snapshot open
        return self._entry(rows[0]) if rows else None

    def append(self, entry):
        b = entry["body"]
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO attestations VALUES (?,?,?,?,?,?,?)",
                    (b["chain_id"], b["seq"], b["run_id"], entry["entry_hash"],
                     entry["signature"], b["key_id"], json.dumps(b, sort_keys=True)),
                )
        except sqlite3.IntegrityError as e:
            if "run_id" in str(e):
                raise DuplicateRun(b["run_id"]) from e
            raise Conflict() from e

    def by_run(self, run_id):
        with self._conn() as c:
            rows = c.execute("SELECT * FROM attestations WHERE run_id=?", (run_id,)).fetchall()
        return self._entry(rows[0]) if rows else None

    def chain(self, chain_id):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM attestations WHERE chain_id=? ORDER BY seq ASC", (chain_id,)
            ).fetchall()
        return [self._entry(r) for r in rows]


def record_attestation(store, private_b64, *, chain_id, run_id, status, raw_input, output,
                       schema_definition=None, created_at=None, retries=20):
    """Read the head, build the next entry, try to append. If we lose a race, re-read and retry."""
    for _ in range(retries):
        last = store.last(chain_id)
        seq = last["body"]["seq"] + 1 if last else 1
        prev = last["entry_hash"] if last else GENESIS
        entry = make_entry(
            private_b64, chain_id=chain_id, seq=seq, prev_hash=prev,
            run_id=run_id, status=status, raw_input=raw_input, output=output,
            schema_definition=schema_definition, created_at=created_at,
        )
        try:
            store.append(entry)
            return entry
        except Conflict:
            continue
    raise RuntimeError("could not append attestation after retries")
