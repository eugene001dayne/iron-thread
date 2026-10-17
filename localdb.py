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


def db_path():
    return os.getenv("IRONTHREAD_DB", "ironthread.db")


def init_db(path=None):
    with sqlite3.connect(path or db_path()) as c:
        c.execute("PRAGMA journal_mode=WAL")
        for table, cols in TABLES.items():
            ddl = ", ".join(f"{name} {typ}" for name, typ in cols.items())
            c.execute(f"CREATE TABLE IF NOT EXISTS {table} ({ddl})")
        c.execute("CREATE INDEX IF NOT EXISTS idx_runs_schema ON validation_runs(schema_id, created_at)")


class LocalClient:
    def __init__(self, path=None):
        self.path = path or db_path()
        init_db(self.path)
        self._c = sqlite3.connect(self.path, timeout=10)
        self._c.row_factory = sqlite3.Row

    # `with get_client() as client:` support
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._c.close()

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

    def _guard(self, fn):
        try:
            return fn()
        except BadQuery as e:
            return LocalResponse(400, {"message": str(e)})
        except sqlite3.IntegrityError as e:
            return LocalResponse(409, {"message": str(e)})

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
