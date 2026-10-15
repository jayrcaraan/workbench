"""
Run SQL against a SQLite file and print the result as a table (the sandbox has no `sqlite3` CLI).

    python ~/tools/sql.py ~/data/trip.db ".schema"
    python ~/tools/sql.py ~/data/trip.db "SELECT category, count(*) FROM items GROUP BY category"
    python ~/tools/sql.py ~/data/trip.db ".tables"
"""

import sqlite3
import sys
from pathlib import Path

db, query = Path(sys.argv[1]).expanduser(), " ".join(sys.argv[2:]).strip()
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
if query in (".tables", ".schema") or query.startswith(".schema "):
    rows = con.execute("SELECT name, sql FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'").fetchall()
    if query == ".tables":
        print("\n".join(r[0] for r in rows))
    else:
        want = query.split(" ", 1)[1] if " " in query else None
        print("\n\n".join(r[1] for r in rows if want in (None, r[0])))
    sys.exit(0)
cur = con.execute(query)
cols = [d[0] for d in cur.description or []]
rows = cur.fetchmany(200)
cells = [cols] + [["" if v is None else str(v) for v in r] for r in rows]
widths = [min(40, max(len(str(r[i])) for r in cells)) for i in range(len(cols))]
for n, r in enumerate(cells):
    print("  ".join(str(v)[:40].ljust(w) for v, w in zip(r, widths)).rstrip())
    if n == 0:
        print("  ".join("-" * w for w in widths))
print(f"({len(rows)} rows{', first 200' if len(rows) == 200 else ''})")
