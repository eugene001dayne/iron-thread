"""
Local, zero-service storage for Iron-Thread.

A tiny PostgREST-compatible client backed by SQLite. It understands exactly the
subset of Supabase's REST API that main.py uses, so main.py's 20 call sites
don't have to change:

  GET    /table?col=eq.x &col=in.(a,b) &col=is.null &or=(c.eq.x,c.is.null)
         &select=a,b &order=created_at.desc &limit=50
  POST   /table            (body = row or list of rows)  -> 201 + [row]
  PATCH  /table?col=eq.x   (body = fields to update)     -> 200 + [rows]
  DELETE /table?col=eq.x
"""
import json
import os
import sqlite3
import threading
from contextlib import closing

JSON_COLS = {"schema_definition", "validated_output", "confidence_flags", "corrected_output"}
BOOL_COLS = {"on_failure", "on_success", "active"}

TABLES = {
    "schemas": {
        "id": "TEXT PRIMARY KEY", "name": "TEXT", "description": "TEXT",
        "schema_definition": "TEXT", "created_at": "TEXT",
    },
    "validation_runs": {
        "id": "TEXT PRIMARY KEY", "schema_id": "TEXT", "raw_ai_output": "TEXT",
        "validated_output": "TEXT", "status": "TEXT", "attempts": "INTEGER",
        "latency_ms": "INTEGER", "model_used": "TEXT", "confidence_score": "REAL",
        "confidence_flags": "TEXT", "run_hash": "TEXT", "previous_hash": "TEXT",
        "created_at": "TEXT",
    },
    "corrections": {
        "id": "TEXT PRIMARY KEY", "run_id": "TEXT", "attempt_number": "INTEGER",
        "failed_output": "TEXT", "corrected_output": "TEXT", "error_reason": "TEXT",
        "created_at": "TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
    },
    "webhooks": {
        "id": "TEXT PRIMARY KEY", "name": "TEXT", "url": "TEXT", "on_failure": "INTEGER",
        "on_success": "INTEGER", "schema_id": "TEXT", "active": "INTEGER", "created_at": "TEXT",
    },
}

SIMPLE_OPS = {"eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
RESERVED = {"select", "order", "limit", "offset", "or"}


class LocalResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code}: {self._data}")


class BadQuery(Exception):
    pass


class StorageBusy(Exception):
    """The database is locked by another writer. Safe to retry shortly."""


def db_path():
    return os.getenv("IRONTHREAD_DB", "ironthread.db")


_INITIALISED = set()
_INIT_LOCK = threading.Lock()


def init_db(path=None):
    """Create tables once per process per database file (not once per request)."""
    path = path or db_path()
    if path in _INITIALISED and os.path.exists(path):
        return
    with _INIT_LOCK:
        if path in _INITIALISED and os.path.exists(path):
            return
        if path in _INITIALISED:
            close_all()  # the file vanished: drop connections that still point at the old one
        _create_tables(path)
        _INITIALISED.add(path)


def _create_tables(path):
    with closing(sqlite3.connect(path)) as c:  # closing(): `with sqlite3.connect()` alone never closes
        c.execute("PRAGMA journal_mode=WAL")
        for table, cols in TABLES.items():
            ddl = ", ".join(f"{name} {typ}" for name, typ in cols.items())
            c.execute(f"CREATE TABLE IF NOT EXISTS {table} ({ddl})")
        c.execute("CREATE INDEX IF NOT EXISTS idx_runs_schema ON validation_runs(schema_id, created_at)")
        c.commit()


# -- persistent per-thread connections -------------------------------------------------------
# Closing the LAST connection to a WAL database checkpoints it and deletes the -wal/-shm files;
# the next connection recreates them. Doing that on every request is brutally slow on Windows
# (measured here: ~98 ms per insert vs ~0.1 ms with a persistent connection).
_tls = threading.local()
_CONN_LOCK = threading.Lock()
_REGISTRY = []  # [(thread, connection)] so close_all() can reach every thread's connection
_GEN = 0


def _close_quietly(conn):
    try:
        conn.close()
    except sqlite3.Error:
        pass


def _prune_dead_threads():
    alive = []
    for thread, conn in _REGISTRY:
        if thread.is_alive():
            alive.append((thread, conn))
        else:
            _close_quietly(conn)
    _REGISTRY[:] = alive


def _connection(path, durable=False):
    """
    One long-lived connection per (thread, database file, durability mode).

    durable=False: synchronous=NORMAL, no fsync per commit. For ordinary tables.
    durable=True:  synchronous=FULL, every commit is fsynced. For the attestation chain,
                   whose entries must survive a power cut.
    """
    if getattr(_tls, "gen", None) != _GEN:
        _tls.conns = {}
        _tls.gen = _GEN
    key = (path, durable)
    conn = _tls.conns.get(key)
    if conn is None:
        # check_same_thread=False only so close_all() may close it; each thread USES only its own.
        conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA synchronous=FULL" if durable else "PRAGMA synchronous=NORMAL")
        _tls.conns[key] = conn
        with _CONN_LOCK:
            _prune_dead_threads()
            _REGISTRY.append((threading.current_thread(), conn))
    return conn


def close_all():
    """Close every thread's connection. For tests, shutdown, or before deleting the DB file."""
    global _GEN
    with _CONN_LOCK:
        _GEN += 1
        entries = list(_REGISTRY)
        _REGISTRY.clear()
    for _, conn in entries:
        _close_quietly(conn)


class LocalClient:
    def __init__(self, path=None):
        self.path = path or db_path()
        init_db(self.path)
        self._c = _connection(self.path)

    # `with get_client() as client:` support
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass  # the connection belongs to the thread and stays open on purpose (see above)

    # ── helpers ──
    @staticmethod
    def _table(path):
        name = path.strip("/")
        if name not in TABLES:
            raise BadQuery(f"unknown table {name!r}")
        return name

    @staticmethod
    def _col(table, col):
        if col not in TABLES[table]:
            raise BadQuery(f"unknown column {col!r} on {table}")
        return col

    @staticmethod
    def _coerce(col, value):
        if col in BOOL_COLS:
            return 1 if str(value).lower() == "true" else 0
        return value

    def _condition(self, table, col, op, raw):
        self._col(table, col)
        if op in SIMPLE_OPS:
            return f"{col} {SIMPLE_OPS[op]} ?", [self._coerce(col, raw)]
        if op == "is":
            return (f"{col} IS NULL", []) if raw == "null" else (f"{col} IS NOT NULL", [])
        if op == "in":
            items = [x for x in raw.strip("()").split(",") if x != ""]
            if not items:
                return "0", []
            return f"{col} IN ({','.join('?' * len(items))})", [self._coerce(col, i) for i in items]
        raise BadQuery(f"unsupported operator {op!r}")

    def _where(self, table, params):
        clauses, args = [], []
        for key, val in (params or {}).items():
            if key == "or":
                parts = [p for p in val.strip("()").split(",") if p]
                sub, sub_args = [], []
                for p in parts:
                    col, op, raw = p.split(".", 2)
                    s, a = self._condition(table, col, op, raw)
                    sub.append(s)
                    sub_args += a
                clauses.append("(" + " OR ".join(sub) + ")")
                args += sub_args
            elif key not in RESERVED:
                op, _, raw = str(val).partition(".")
                s, a = self._condition(table, key, op, raw)
                clauses.append(s)
                args += a
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", args

    @staticmethod
    def _encode(col, value):
        if value is None:
            return None
        if col in JSON_COLS:
            return json.dumps(value)
        if col in BOOL_COLS:
            return 1 if value else 0
        return value

    @staticmethod
    def _decode(row, columns):
        out = {}
        for col in columns:
            v = row[col]
            if v is not None and col in JSON_COLS:
                v = json.loads(v)
            elif v is not None and col in BOOL_COLS:
                v = bool(v)
            out[col] = v
        return out

    def _rollback(self):
        try:
            self._c.rollback()
        except sqlite3.Error:
            pass

    def _guard(self, fn):
        try:
            return fn()
        except BadQuery as e:
            self._rollback()
            return LocalResponse(400, {"message": str(e)})
        except sqlite3.IntegrityError as e:
            self._rollback()
            return LocalResponse(409, {"message": str(e)})
        except sqlite3.OperationalError as e:
            self._rollback()
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                raise StorageBusy(str(e)) from e
            raise
        except BaseException:
            self._rollback()  # never leave a half-finished transaction on a long-lived connection
            raise

    # ── verbs ──
    def get(self, path, params=None):
        def run():
            table = self._table(path)
            params_ = dict(params or {})
            select = params_.get("select", "*")
            columns = list(TABLES[table]) if select == "*" else [self._col(table, c) for c in select.split(",")]
            where, args = self._where(table, params_)
            sql = f"SELECT {','.join(columns)} FROM {table}{where}"
            if "order" in params_:
                parts = []
                for item in params_["order"].split(","):
                    col, _, direction = item.partition(".")
                    parts.append(f"{self._col(table, col)} {'DESC' if direction == 'desc' else 'ASC'}")
                sql += " ORDER BY " + ", ".join(parts)
            if "limit" in params_:
                sql += f" LIMIT {int(params_['limit'])}"
                if "offset" in params_:
                    sql += f" OFFSET {int(params_['offset'])}"
            rows = self._c.execute(sql, args).fetchall()
            return LocalResponse(200, [self._decode(r, columns) for r in rows])
        return self._guard(run)

    def post(self, path, json=None, params=None):
        def run():
            table = self._table(path)
            rows = json if isinstance(json, list) else [json]
            for row in rows:
                cols = [self._col(table, c) for c in row]
                self._c.execute(
                    f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [self._encode(c, row[c]) for c in cols],
                )
            self._c.commit()
            return LocalResponse(201, rows)
        return self._guard(run)

    def patch(self, path, params=None, json=None):
        def run():
            table = self._table(path)
            if not json:
                raise BadQuery("nothing to update")
            cols = [self._col(table, c) for c in json]
            where, args = self._where(table, params)
            self._c.execute(
                f"UPDATE {table} SET {', '.join(c + '=?' for c in cols)}{where}",
                [self._encode(c, json[c]) for c in cols] + args,
            )
            self._c.commit()
            return self.get(path, params)
        return self._guard(run)

    def delete(self, path, params=None):
        def run():
            table = self._table(path)
            where, args = self._where(table, params)
            self._c.execute(f"DELETE FROM {table}{where}", args)
            self._c.commit()
            return LocalResponse(204, [])
        return self._guard(run)
