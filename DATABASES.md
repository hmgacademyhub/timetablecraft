# 🗄️ TimetableCraft — Database Backends

> *A product of **HMG Technologies** — a subsidiary of **HMG Concepts**.*

TimetableCraft is **database-agnostic**. It ships with a zero-config SQLite default so any school can run it without signing up for a cloud DB, and supports PostgreSQL when the school grows into multi-admin / cloud-hosted territory.

This page is for technically-curious admins and contributors. For a step-by-step deployment walkthrough see [`DEPLOYMENT.md`](DEPLOYMENT.md); for typical usage you don't need to read this at all.

---

## TL;DR

| | SQLite *(default)* | PostgreSQL *(optional)* |
|---|---|---|
| **Setup cost** | None | DB account + secrets |
| **Concurrent admins** | 1 (safe) – 2 (OK with WAL) | Many |
| **Data lives** | One file (`timetablecraft.db`) | Managed cluster |
| **Survives Streamlit Cloud redeploys** | ❌ (ephemeral disk) | ✅ |
| **Backup** | `cp` the file | `pg_dump` / provider-managed |
| **Performance** | Excellent for one school | Excellent at any scale |
| **Cost** | ₦0 | Free tier on Supabase / Neon / Render |

If in doubt → start with SQLite. You can switch later without any code change.

---

## Backend auto-selection

`db.py` runs `_detect_backend()` at import time and picks the first match from this list:

| Priority | Source | If matched → |
|:--:|---|---|
| 1 | `TIMETABLECRAFT_DB=sqlite\|postgres` env var | explicit override |
| 2 | `DATABASE_URL=postgresql://…` | Postgres |
| 3 | `DATABASE_URL=sqlite:///…` | SQLite |
| 4 | `st.secrets["postgres"]` block | Postgres |
| 5 | `st.secrets["supabase"]` block *(legacy)* | Postgres |
| 6 | `PGHOST` + `PGDATABASE` + `PGUSER` env vars | Postgres |
| 7 | (fallback) | SQLite at `./timetablecraft.db` |

You can override the SQLite file location with `TIMETABLECRAFT_DB_PATH`.

The active backend is exposed via:

```python
from db import get_backend, backend_summary
print(get_backend())        # 'sqlite' or 'postgres'
print(backend_summary())    # human-readable summary
```

…and shown as a sidebar badge in the running app (📦 SQLite / 🐘 Postgres).

---

## How the SQL stays portable

`db.py` contains a one-pass dialect translator (`_to_sqlite_sql`) that runs on every query when SQLite is active. It rewrites:

| Postgres SQL | → SQLite SQL |
|---|---|
| `SERIAL PRIMARY KEY` | `INTEGER PRIMARY KEY AUTOINCREMENT` |
| `TIMESTAMPTZ` | `TIMESTAMP` |
| `BOOLEAN` | `INTEGER` |
| `NOW()` | `CURRENT_TIMESTAMP` |
| `DEFAULT FALSE` / `DEFAULT TRUE` | `DEFAULT 0` / `DEFAULT 1` |
| `%s` placeholders | `?` placeholders |

`ON CONFLICT ... DO UPDATE SET col=EXCLUDED.col` and `... RETURNING id` are natively supported on both engines (SQLite ≥ 3.24 / 3.35 respectively), so they need no translation.

Python booleans in parameters are coerced to 0/1 for the SQLite driver; psycopg2 handles them natively.

Row access works the same way on both backends because both expose dict-style access:

```python
row = cur.fetchone()
row["teacher_name"]   # works on both
```

---

## Switching backends

### SQLite → Postgres (no data loss)

1. Use **📤 Export → Master CSV** to dump everything.
2. Add a `[postgres]` block to `.streamlit/secrets.toml`.
3. Restart the app. Sidebar badge flips to 🐘 Postgres. Database is empty — seeder will offer to re-seed demo data.
4. Re-import your data via the bulk-import tabs on Teachers / Subjects / Classes / Students.

(Direct cross-engine migration is on the roadmap — for now, CSV round-trip is the supported path.)

### Postgres → SQLite

Same as above, in reverse. Most users will never need this — but the option exists.

---

## Multi-user safety

Both backends are guarded by a process-level `threading.RLock` in `_DB_LOCK`:

- **SQLite:** opened with `check_same_thread=False`, WAL journal mode, 5-second busy timeout, 30-second connection timeout. Safe for **one admin and read-heavy concurrent viewers**.
- **PostgreSQL:** the psycopg2 connection isn't thread-safe by default. The RLock serialises Streamlit-session access. Safe for **many concurrent admins**.

If you regularly have ≥ 3 admins editing simultaneously, run Postgres.

---

## Schema migrations

Every backend goes through the same two-step boot:

```
init_db()       — CREATE TABLE IF NOT EXISTS for v1-v4 tables
migrate_v5()    — CREATE TABLE IF NOT EXISTS for v5 tables
                  (students, exam_slots, calendar_events,
                   version_locks, school_branding)
```

Both are idempotent — safe to call on every cold start.

For new schema changes, add a `migrate_vN()` function in `db.py` and call it from `startup.seed_on_cold_start()` after `init_db()`.

---

## File anatomy (SQLite mode)

```
timetablecraft.db           ← the SQLite database file (your data)
timetablecraft.db-wal       ← write-ahead log    (created by WAL mode)
timetablecraft.db-shm       ← shared memory file (created by WAL mode)
```

All three are gitignored. **Back up all three together** if the app is running (or stop the app first and back up just the `.db` file).

---

*Maintained by **Adewale Samson Adeagbo**, Founder of HMG Concepts. Questions: hello@hmgconcepts.com*
