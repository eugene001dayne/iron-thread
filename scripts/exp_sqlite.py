"""
The experiment behind the persistent-connection design: three ways of doing 500 SQLite writes.

    python scripts/exp_sqlite.py

A) a new connection per write      B) the same plus an idle "keeper" connection      C) one persistent connection
On Windows this measured about 98 ms, 9.8 ms and 0.1 ms per write. It has no dependency on Iron-Thread.
"""
import os
import sqlite3
import sys
import tempfile
import time

N = 500


def fresh_db():
    p = os.path.join(tempfile.mkdtemp(), "t.db")
    c = sqlite3.connect(p)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE t(x)")
    c.commit()
    c.close()
    return p


def insert_with_new_connection(p, i):
    c = sqlite3.connect(p, timeout=10)
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("INSERT INTO t VALUES(?)", (i,))
    c.commit()
    c.close()


print("Python", sys.version.split()[0], "| SQLite", sqlite3.sqlite_version)

p = fresh_db()
t = time.perf_counter()
for i in range(N):
    insert_with_new_connection(p, i)
a = time.perf_counter() - t
print(f"A) new connection per insert:            {a:6.2f}s  ({a / N * 1000:5.1f} ms each)")

p = fresh_db()
keeper = sqlite3.connect(p)
keeper.execute("SELECT count(*) FROM t").fetchall()
t = time.perf_counter()
for i in range(N):
    insert_with_new_connection(p, i)
b = time.perf_counter() - t
keeper.close()
print(f"B) new connection + idle keeper:         {b:6.2f}s  ({b / N * 1000:5.1f} ms each)")

p = fresh_db()
c = sqlite3.connect(p, timeout=10)
c.execute("PRAGMA synchronous=NORMAL")
t = time.perf_counter()
for i in range(N):
    c.execute("INSERT INTO t VALUES(?)", (i,))
    c.commit()
cc = time.perf_counter() - t
c.close()
print(f"C) one persistent connection:            {cc:6.2f}s  ({cc / N * 1000:5.1f} ms each)")
