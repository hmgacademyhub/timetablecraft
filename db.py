"""
================================================================================
TimetableCraft — db.py  (v5.2 — Backend-Agnostic Data Layer)
HMG Technologies · a subsidiary of HMG Concepts
================================================================================

Supports TWO database backends, transparently, with the SAME public API:

  • SQLite  (DEFAULT)  — zero config, single file `timetablecraft.db`.
                          Perfect for a single-school deployment.
  • PostgreSQL          — opt-in upgrade for multi-user / cloud.
                          Works with Supabase, Render, Railway, Neon,
                          self-hosted, etc.

Backend is auto-selected by this order of priority:

  1. Env var  TIMETABLECRAFT_DB=sqlite|postgres
  2. Env var  DATABASE_URL=postgresql://…   → postgres
  3. Env var  DATABASE_URL=sqlite:///…      → sqlite
  4. st.secrets["postgres"]  block present → postgres
  5. st.secrets["supabase"]  block present → postgres  (back-compat)
  6. Env vars PGHOST + PGDATABASE + PGUSER  → postgres
  7. Fallback → SQLite at  ./timetablecraft.db   (or TIMETABLECRAFT_DB_PATH)

All call sites (scheduler.py, pdf_gen.py, app.py, startup.py) work
UNCHANGED across both backends — the SQL is normalised on the fly.
================================================================================
"""

import json
import os
import sqlite3
import threading
import streamlit as st

# psycopg2 is OPTIONAL — only required when the user chooses Postgres.
try:
    import psycopg2
    import psycopg2.extras
    _HAS_PSYCOPG2 = True
except ImportError:
    psycopg2 = None
    _HAS_PSYCOPG2 = False

# ── Default config values (seeded on first init) ───────────────────────────────
DEFAULT_CONFIG = {
    "school_name":            "HMG Academy",
    "mon_thu_duration":       "40",
    "fri_duration":           "30",
    "periods_per_day":        "8",
    "day_start_time":         "08:00",
    "assembly_duration":      "15",
    "break_after_slot":       "4",
    "break_duration":         "20",
    "double_periods_enabled": "true",
    "school_days":            "Monday,Tuesday,Wednesday,Thursday,Friday",
    "current_term":           "First Term",
    "current_session":        "2024/2025",
    "active_version":         "v1",
}

# Print init/migration messages at most once per process (tidy cloud logs)
_SCHEMA_LOGGED = False
_MIGRATION_LOGGED = False
# Serialise access to the cached connection (psycopg2 conns aren't
# thread-safe, and SQLite check_same_thread=False needs serialisation).
_DB_LOCK = threading.RLock()


# ══════════════════════════════════════════════════════════════════════════════
# Backend selection
# ══════════════════════════════════════════════════════════════════════════════
def _detect_backend():
    """
    Return ('sqlite', {'path': '...'})   or   ('postgres', {...creds...}).

    See the module docstring for the priority order.  This function is
    deliberately tolerant — any failure to read st.secrets falls back to
    env vars, then to SQLite — so the app never refuses to boot just
    because secrets aren't configured.
    """
    # 1) Explicit override
    forced = (os.environ.get("TIMETABLECRAFT_DB") or "").strip().lower()
    if forced == "sqlite":
        return ("sqlite", {"path": _sqlite_path()})
    if forced in ("postgres", "postgresql", "pg"):
        return ("postgres", _postgres_creds_from_anywhere())

    # 2/3) DATABASE_URL
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        if url.startswith(("postgres://", "postgresql://")):
            return ("postgres", _parse_pg_url(url))
        # SQLAlchemy convention:
        #   sqlite:///relative/path.db   → relative
        #   sqlite:////absolute/path.db  → absolute
        #   sqlite://                    → in-memory
        if url == "sqlite://":
            return ("sqlite", {"path": ":memory:"})
        if url.startswith("sqlite:////"):    # 4 slashes → absolute
            return ("sqlite", {"path": url[len("sqlite:///"):]})  # keep one leading /
        if url.startswith("sqlite:///"):     # 3 slashes → relative
            return ("sqlite", {"path": url[len("sqlite:///"):]})

    # 4/5) st.secrets
    for section in ("postgres", "supabase"):
        try:
            cfg = dict(st.secrets[section])
            if cfg.get("host") and cfg.get("dbname") and cfg.get("user"):
                return ("postgres", cfg)
        except Exception:
            pass

    # 6) PG env vars
    if os.environ.get("PGHOST") and os.environ.get("PGDATABASE") \
            and os.environ.get("PGUSER"):
        return ("postgres", {
            "host":     os.environ["PGHOST"],
            "port":     int(os.environ.get("PGPORT", 5432)),
            "dbname":   os.environ["PGDATABASE"],
            "user":     os.environ["PGUSER"],
            "password": os.environ.get("PGPASSWORD", ""),
            "sslmode":  os.environ.get("PGSSLMODE", "require"),
        })

    # 7) Default → SQLite (zero-config)
    return ("sqlite", {"path": _sqlite_path()})


def _sqlite_path() -> str:
    """Where to put the SQLite file. Override with TIMETABLECRAFT_DB_PATH."""
    return os.environ.get("TIMETABLECRAFT_DB_PATH", "timetablecraft.db")


def _postgres_creds_from_anywhere():
    """Used when the user explicitly forced TIMETABLECRAFT_DB=postgres."""
    for section in ("postgres", "supabase"):
        try:
            cfg = dict(st.secrets[section])
            if cfg.get("host"):
                return cfg
        except Exception:
            pass
    if os.environ.get("PGHOST"):
        return {
            "host":     os.environ["PGHOST"],
            "port":     int(os.environ.get("PGPORT", 5432)),
            "dbname":   os.environ.get("PGDATABASE", "postgres"),
            "user":     os.environ.get("PGUSER", "postgres"),
            "password": os.environ.get("PGPASSWORD", ""),
            "sslmode":  os.environ.get("PGSSLMODE", "require"),
        }
    raise RuntimeError(
        "TIMETABLECRAFT_DB=postgres was set but no Postgres credentials "
        "were found (looked at st.secrets['postgres'], "
        "st.secrets['supabase'], and PG* env vars)."
    )


def _parse_pg_url(url: str) -> dict:
    """Minimal postgresql://user:pass@host:port/db parser (no deps)."""
    from urllib.parse import urlparse, parse_qs
    p = urlparse(url)
    qs = {k: v[0] for k, v in parse_qs(p.query).items()}
    return {
        "host":     p.hostname or "localhost",
        "port":     int(p.port or 5432),
        "dbname":   (p.path or "/postgres").lstrip("/") or "postgres",
        "user":     p.username or "postgres",
        "password": p.password or "",
        "sslmode":  qs.get("sslmode", "prefer"),
    }


# Resolve once at import time so the rest of the module knows which dialect to speak.
_BACKEND, _BACKEND_CFG = _detect_backend()


def get_backend() -> str:
    """Return the active backend name ('sqlite' or 'postgres')."""
    return _BACKEND


def backend_summary() -> str:
    """Short human-readable summary — shown in the UI sidebar / about card."""
    if _BACKEND == "sqlite":
        return f"SQLite · file: {_BACKEND_CFG['path']}"
    host = _BACKEND_CFG.get("host", "?")
    db   = _BACKEND_CFG.get("dbname", "?")
    return f"PostgreSQL · {host}/{db}"


# ══════════════════════════════════════════════════════════════════════════════
# SQL dialect normalisation
# ══════════════════════════════════════════════════════════════════════════════
def _to_sqlite_sql(sql: str) -> str:
    """
    Translate the Postgres-flavoured SQL written below into SQLite-flavoured
    SQL, on the fly. Idempotent — safe to call on already-translated SQL.

    Translations:
      SERIAL PRIMARY KEY  → INTEGER PRIMARY KEY AUTOINCREMENT
      TIMESTAMPTZ         → TIMESTAMP
      BOOLEAN             → INTEGER       (we pass 0/1)
      NOW()               → CURRENT_TIMESTAMP
      FALSE / TRUE        → 0 / 1
      %s   placeholders   → ?

    The dialect of ON CONFLICT … DO UPDATE SET col=EXCLUDED.col is
    identical on SQLite ≥ 3.24 and PostgreSQL, and RETURNING works
    identically on SQLite ≥ 3.35 — so neither needs translating.
    """
    out = sql
    # Type translations
    out = out.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    out = out.replace("TIMESTAMPTZ",        "TIMESTAMP")
    out = out.replace("BOOLEAN",            "INTEGER")
    out = out.replace("NOW()",              "CURRENT_TIMESTAMP")
    # Boolean literals only as standalone words (don't touch column names)
    # SQLite ≥ 3.23 actually supports TRUE/FALSE keywords so this is just for safety.
    out = out.replace("DEFAULT FALSE", "DEFAULT 0")
    out = out.replace("DEFAULT TRUE",  "DEFAULT 1")
    # Placeholders
    out = out.replace("%s", "?")
    return out


def _coerce_params(params):
    """Convert Python booleans to 0/1 for SQLite (psycopg2 handles bools natively)."""
    if params is None:
        return params
    if isinstance(params, dict):
        return {k: (int(v) if isinstance(v, bool) else v) for k, v in params.items()}
    return [int(p) if isinstance(p, bool) else p for p in params]


# ══════════════════════════════════════════════════════════════════════════════
# Connection layer (uniform API across both backends)
# ══════════════════════════════════════════════════════════════════════════════
class _DictRowCursor:
    """
    Thin wrapper that makes a SQLite cursor look like psycopg2's
    RealDictCursor: row access by column name AND by index, fetchone()
    returns dict-like, and SQL gets translated on the fly.
    """
    def __init__(self, sqlite_cursor):
        self._cur = sqlite_cursor

    def execute(self, sql, params=None):
        sql = _to_sqlite_sql(sql)
        if params is None:
            self._cur.execute(sql)
        else:
            self._cur.execute(sql, _coerce_params(params))
        return self

    def executemany(self, sql, seq):
        sql = _to_sqlite_sql(sql)
        self._cur.executemany(sql, [_coerce_params(p) for p in seq])
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(r) for r in self._cur.fetchall()]

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    def close(self):
        self._cur.close()


@st.cache_resource(show_spinner=False)
def _get_pool():
    """
    Cache ONE connection per process. Both backends share the same RLock,
    so concurrent Streamlit sessions are serialised safely.
    """
    if _BACKEND == "sqlite":
        # check_same_thread=False is safe because _DB_LOCK serialises all access.
        conn = sqlite3.connect(
            _BACKEND_CFG["path"],
            check_same_thread=False,
            isolation_level="DEFERRED",   # explicit commit() like psycopg2
            timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        # Sensible pragmas
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    # Postgres
    if not _HAS_PSYCOPG2:
        raise RuntimeError(
            "Postgres backend selected but the `psycopg2-binary` package is "
            "not installed. Install it with `pip install psycopg2-binary` "
            "or set TIMETABLECRAFT_DB=sqlite to use the zero-config SQLite "
            "backend."
        )
    cfg = _BACKEND_CFG
    conn = psycopg2.connect(
        host=cfg["host"],
        port=int(cfg.get("port", 5432)),
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg.get("password", ""),
        sslmode=cfg.get("sslmode", "require"),
        connect_timeout=10,
    )
    conn.autocommit = False
    return conn


def _reset_pool():
    """Close & forget the cached connection (call on any fatal DB error)."""
    try:
        conn = _get_pool()
        try:
            conn.close()
        except Exception:
            pass
    except Exception:
        pass
    try:
        _get_pool.clear()
    except Exception:
        pass


def get_conn():
    """
    Return the cached connection, reconnecting if it's been dropped
    (Postgres idle-disconnect, SQLite file unlinked, etc.). Guarded by
    a module-level RLock so concurrent Streamlit sessions are safe.
    """
    with _DB_LOCK:
        try:
            conn = _get_pool()
        except Exception:
            _reset_pool()
            raise
        try:
            if _BACKEND == "sqlite":
                conn.execute("SELECT 1").fetchone()
            else:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.close()
                conn.rollback()   # don't leave an idle-in-transaction
            return conn
        except Exception:
            _reset_pool()
            return _get_pool()


def _cur(conn):
    """
    Return a dict-returning cursor. Same calling convention for both
    backends — every helper below stays unchanged.
    """
    if _BACKEND == "sqlite":
        return _DictRowCursor(conn.cursor())
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ══════════════════════════════════════════════════════════════════════════════
# Schema — init_db()
# ══════════════════════════════════════════════════════════════════════════════
def init_db():
    """
    Create all tables if they do not exist.
    Idempotent — safe to call on every application startup.
    """
    conn = get_conn()
    cur  = _cur(conn)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            id                   SERIAL PRIMARY KEY,
            name                 TEXT NOT NULL UNIQUE,
            subjects             TEXT NOT NULL DEFAULT '[]',
            staff_type           TEXT NOT NULL DEFAULT 'fulltime'
                                     CHECK(staff_type IN ('fulltime','parttime')),
            available_days       TEXT NOT NULL
                                     DEFAULT 'Monday,Tuesday,Wednesday,Thursday,Friday',
            max_periods_per_week INTEGER DEFAULT 30,
            created_at           TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id                  SERIAL PRIMARY KEY,
            name                TEXT NOT NULL UNIQUE,
            periods_per_week    INTEGER NOT NULL DEFAULT 4,
            assigned_teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
            color_hex           TEXT DEFAULT '#4A90D9',
            allow_double        BOOLEAN DEFAULT FALSE,
            created_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id         SERIAL PRIMARY KEY,
            name       TEXT NOT NULL,
            arm        TEXT NOT NULL DEFAULT 'A',
            level      TEXT NOT NULL DEFAULT 'JSS',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(name, arm)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS class_subjects (
            id         SERIAL PRIMARY KEY,
            class_id   INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            UNIQUE(class_id, subject_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS special_slots (
            id        SERIAL PRIMARY KEY,
            label     TEXT NOT NULL,
            position  INTEGER NOT NULL,
            duration  INTEGER NOT NULL DEFAULT 15,
            color_hex TEXT DEFAULT '#F5A623',
            days      TEXT DEFAULT 'Monday,Tuesday,Wednesday,Thursday,Friday'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS timetable_versions (
            id          SERIAL PRIMARY KEY,
            version_tag TEXT NOT NULL UNIQUE,
            label       TEXT NOT NULL,
            term        TEXT NOT NULL DEFAULT 'First Term',
            session     TEXT NOT NULL DEFAULT '2024/2025',
            notes       TEXT DEFAULT '',
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS periods (
            id                SERIAL PRIMARY KEY,
            day               TEXT NOT NULL,
            slot_number       INTEGER NOT NULL,
            start_time        TEXT NOT NULL,
            end_time          TEXT NOT NULL,
            class_id          INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            subject_id        INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
            teacher_id        INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
            is_double         BOOLEAN DEFAULT FALSE,
            timetable_version TEXT DEFAULT 'v1',
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(day, slot_number, class_id, timetable_version)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS school_config (
            id    SERIAL PRIMARY KEY,
            key   TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL
        )
    """)

    # ── Substitutions ─────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS substitutions (
            id                    SERIAL PRIMARY KEY,
            absence_date          TEXT NOT NULL,
            absent_teacher_id     INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
            substitute_teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
            class_id              INTEGER REFERENCES classes(id) ON DELETE CASCADE,
            subject_id            INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
            slot_number           INTEGER NOT NULL,
            day                   TEXT NOT NULL,
            reason                TEXT DEFAULT \'\',
            status                TEXT DEFAULT \'pending\'
                                      CHECK(status IN (\'pending\',\'confirmed\',\'cancelled\')),
            timetable_version     TEXT DEFAULT \'v1\',
            created_at            TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ── Student Notices ───────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notices (
            id         SERIAL PRIMARY KEY,
            title      TEXT NOT NULL,
            body       TEXT NOT NULL,
            class_id   INTEGER REFERENCES classes(id) ON DELETE CASCADE,
            subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
            priority   TEXT DEFAULT \'normal\'
                           CHECK(priority IN (\'low\',\'normal\',\'high\',\'urgent\')),
            expires_on TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ── Change Log ────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS change_log (
            id          SERIAL PRIMARY KEY,
            action      TEXT NOT NULL,
            entity      TEXT NOT NULL,
            entity_id   INTEGER,
            description TEXT NOT NULL,
            changed_by  TEXT DEFAULT \'admin\',
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Seed default config (skip existing keys)
    for key, value in DEFAULT_CONFIG.items():
        cur.execute("""
            INSERT INTO school_config (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO NOTHING
        """, (key, value))

    # Seed default version
    cur.execute("""
        INSERT INTO timetable_versions (version_tag, label, term, session)
        VALUES ('v1', 'Version 1 — First Term', 'First Term', '2024/2025')
        ON CONFLICT (version_tag) DO NOTHING
    """)

    # Seed default special slots
    cur.execute("""
        INSERT INTO special_slots (id, label, position, duration, color_hex)
        VALUES (1, 'Assembly', 0, 15, '#F5A623')
        ON CONFLICT (id) DO NOTHING
    """)
    cur.execute("""
        INSERT INTO special_slots (id, label, position, duration, color_hex)
        VALUES (2, 'Break', 4, 20, '#48BB78')
        ON CONFLICT (id) DO NOTHING
    """)

    conn.commit()
    global _SCHEMA_LOGGED
    if not _SCHEMA_LOGGED:
        print(f"[db] ✅ Schema ready ({_BACKEND}) — all tables initialised.")
        _SCHEMA_LOGGED = True


# ══════════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════════
def get_config(key, default=None):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT value FROM school_config WHERE key=%s", (key,))
    row = cur.fetchone()
    return row["value"] if row else default


def set_config(key, value):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO school_config (key, value) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
    """, (key, str(value)))
    conn.commit()


def get_all_config():
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT key, value FROM school_config")
    return {r["key"]: r["value"] for r in cur.fetchall()}


# ══════════════════════════════════════════════════════════════════════════════
# Timetable Versions
# ══════════════════════════════════════════════════════════════════════════════
def get_all_versions():
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT * FROM timetable_versions ORDER BY created_at DESC")
    return [dict(r) for r in cur.fetchall()]


def add_version(version_tag, label, term, session, notes=""):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO timetable_versions (version_tag, label, term, session, notes)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (version_tag) DO NOTHING
    """, (version_tag, label, term, session, notes))
    conn.commit()
    print(f"[db] ✅ Version: {version_tag}")


def get_active_version():
    return get_config("active_version", "v1")


def set_active_version(version_tag):
    set_config("active_version", version_tag)
    print(f"[db] ✅ Active version → {version_tag}")


def delete_version(version_tag):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM periods WHERE timetable_version=%s", (version_tag,))
    cur.execute("DELETE FROM timetable_versions WHERE version_tag=%s", (version_tag,))
    conn.commit()
    print(f"[db] 🗑️  Version deleted: {version_tag}")


# ══════════════════════════════════════════════════════════════════════════════
# Special Slots
# ══════════════════════════════════════════════════════════════════════════════
def get_all_special_slots():
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT * FROM special_slots ORDER BY position")
    return [dict(r) for r in cur.fetchall()]


def add_special_slot(label, position, duration,
                     color_hex="#F5A623",
                     days="Monday,Tuesday,Wednesday,Thursday,Friday"):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO special_slots (label, position, duration, color_hex, days)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    """, (label, position, duration, color_hex, days))
    sid = cur.fetchone()["id"]
    conn.commit()
    print(f"[db] ✅ Special slot: {label}")
    return sid


def update_special_slot(slot_id, label, position, duration, color_hex, days):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        UPDATE special_slots
        SET label=%s, position=%s, duration=%s, color_hex=%s, days=%s
        WHERE id=%s
    """, (label, position, duration, color_hex, days, slot_id))
    conn.commit()


def delete_special_slot(slot_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM special_slots WHERE id=%s", (slot_id,))
    conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# Teachers
# ══════════════════════════════════════════════════════════════════════════════
def add_teacher(name, subjects_ids, staff_type="fulltime",
                available_days="Monday,Tuesday,Wednesday,Thursday,Friday",
                max_periods=30):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO teachers (name, subjects, staff_type, available_days, max_periods_per_week)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    """, (name, json.dumps(subjects_ids), staff_type, available_days, max_periods))
    tid = cur.fetchone()["id"]
    conn.commit()
    print(f"[db] ✅ Teacher: {name} (ID={tid})")
    return tid


def get_all_teachers():
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT * FROM teachers ORDER BY name")
    result = []
    for r in cur.fetchall():
        d = dict(r)
        d["subjects"] = json.loads(d["subjects"])
        result.append(d)
    return result


def get_teacher(teacher_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT * FROM teachers WHERE id=%s", (teacher_id,))
    row = cur.fetchone()
    if row:
        d = dict(row)
        d["subjects"] = json.loads(d["subjects"])
        return d
    return None


def update_teacher(teacher_id, name, subjects_ids, staff_type, available_days, max_periods):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        UPDATE teachers
        SET name=%s, subjects=%s, staff_type=%s, available_days=%s, max_periods_per_week=%s
        WHERE id=%s
    """, (name, json.dumps(subjects_ids), staff_type, available_days, max_periods, teacher_id))
    conn.commit()
    print(f"[db] ✅ Teacher updated: ID={teacher_id}")


def delete_teacher(teacher_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM teachers WHERE id=%s", (teacher_id,))
    conn.commit()
    print(f"[db] 🗑️  Teacher deleted: ID={teacher_id}")


# ══════════════════════════════════════════════════════════════════════════════
# Subjects
# ══════════════════════════════════════════════════════════════════════════════
def add_subject(name, periods_per_week=4, assigned_teacher_id=None,
                color_hex="#4A90D9", allow_double=False):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO subjects (name, periods_per_week, assigned_teacher_id, color_hex, allow_double)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    """, (name, periods_per_week, assigned_teacher_id, color_hex, bool(allow_double)))
    sid = cur.fetchone()["id"]
    conn.commit()
    print(f"[db] ✅ Subject: {name} (ID={sid})")
    return sid


def get_all_subjects():
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        SELECT s.*, t.name AS teacher_name
        FROM subjects s
        LEFT JOIN teachers t ON s.assigned_teacher_id = t.id
        ORDER BY s.name
    """)
    return [dict(r) for r in cur.fetchall()]


def get_subject(subject_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT * FROM subjects WHERE id=%s", (subject_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def update_subject(subject_id, name, periods_per_week, assigned_teacher_id,
                   color_hex, allow_double):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        UPDATE subjects
        SET name=%s, periods_per_week=%s, assigned_teacher_id=%s,
            color_hex=%s, allow_double=%s
        WHERE id=%s
    """, (name, periods_per_week, assigned_teacher_id,
          color_hex, bool(allow_double), subject_id))
    conn.commit()
    print(f"[db] ✅ Subject updated: ID={subject_id}")


def delete_subject(subject_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM subjects WHERE id=%s", (subject_id,))
    conn.commit()
    print(f"[db] 🗑️  Subject deleted: ID={subject_id}")


# ══════════════════════════════════════════════════════════════════════════════
# Classes
# ══════════════════════════════════════════════════════════════════════════════
def add_class(name, arm="A", level="JSS"):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute(
        "INSERT INTO classes (name, arm, level) VALUES (%s, %s, %s) RETURNING id",
        (name, arm, level)
    )
    cid = cur.fetchone()["id"]
    conn.commit()
    print(f"[db] ✅ Class: {name} {arm} (ID={cid})")
    return cid


def get_all_classes():
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT * FROM classes ORDER BY level, name, arm")
    return [dict(r) for r in cur.fetchall()]


def get_class(class_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT * FROM classes WHERE id=%s", (class_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def update_class(class_id, name, arm, level):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute(
        "UPDATE classes SET name=%s, arm=%s, level=%s WHERE id=%s",
        (name, arm, level, class_id)
    )
    conn.commit()


def delete_class(class_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM classes WHERE id=%s", (class_id,))
    conn.commit()
    print(f"[db] 🗑️  Class deleted: ID={class_id}")


# ══════════════════════════════════════════════════════════════════════════════
# Class–Subject Mapping
# ══════════════════════════════════════════════════════════════════════════════
def assign_subjects_to_class(class_id, subject_ids):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM class_subjects WHERE class_id=%s", (class_id,))
    for sid in subject_ids:
        cur.execute("""
            INSERT INTO class_subjects (class_id, subject_id) VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (class_id, sid))
    conn.commit()
    print(f"[db] ✅ Class {class_id} → {len(subject_ids)} subjects")


def get_subjects_for_class(class_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        SELECT s.*, t.name AS teacher_name
        FROM class_subjects cs
        JOIN subjects s ON cs.subject_id = s.id
        LEFT JOIN teachers t ON s.assigned_teacher_id = t.id
        WHERE cs.class_id = %s
        ORDER BY s.name
    """, (class_id,))
    return [dict(r) for r in cur.fetchall()]


def get_subject_ids_for_class(class_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT subject_id FROM class_subjects WHERE class_id=%s", (class_id,))
    return [r["subject_id"] for r in cur.fetchall()]


def bulk_assign_subjects_by_level(level, subject_ids):
    classes = get_all_classes()
    count = 0
    for c in classes:
        if c["level"] == level:
            assign_subjects_to_class(c["id"], subject_ids)
            count += 1
    print(f"[db] ✅ Bulk: {len(subject_ids)} subjects → {count} {level} classes")
    return count


# ══════════════════════════════════════════════════════════════════════════════
# Periods
# ══════════════════════════════════════════════════════════════════════════════
def insert_period(day, slot_number, start_time, end_time,
                  class_id, subject_id, teacher_id,
                  is_double=False, version="v1"):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO periods
            (day, slot_number, start_time, end_time, class_id,
             subject_id, teacher_id, is_double, timetable_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (day, slot_number, class_id, timetable_version)
        DO UPDATE SET
            start_time  = EXCLUDED.start_time,
            end_time    = EXCLUDED.end_time,
            subject_id  = EXCLUDED.subject_id,
            teacher_id  = EXCLUDED.teacher_id,
            is_double   = EXCLUDED.is_double
    """, (day, slot_number, start_time, end_time,
          class_id, subject_id, teacher_id, bool(is_double), version))
    conn.commit()


def clear_periods(version=None):
    conn = get_conn()
    cur  = _cur(conn)
    if version:
        cur.execute("DELETE FROM periods WHERE timetable_version=%s", (version,))
    else:
        cur.execute("DELETE FROM periods")
    conn.commit()
    print(f"[db] 🗑️  Periods cleared (version={version or 'ALL'})")


def get_periods_for_class(class_id, version=None):
    conn = get_conn()
    cur  = _cur(conn)
    ver  = version or get_active_version()
    cur.execute("""
        SELECT p.*, s.name AS subject_name, s.color_hex, t.name AS teacher_name
        FROM periods p
        LEFT JOIN subjects s ON p.subject_id = s.id
        LEFT JOIN teachers t ON p.teacher_id = t.id
        WHERE p.class_id=%s AND p.timetable_version=%s
        ORDER BY p.day, p.slot_number
    """, (class_id, ver))
    return [dict(r) for r in cur.fetchall()]


def get_periods_for_teacher(teacher_id, version=None):
    conn = get_conn()
    cur  = _cur(conn)
    ver  = version or get_active_version()
    cur.execute("""
        SELECT p.*, s.name AS subject_name, c.name AS class_name, c.arm
        FROM periods p
        LEFT JOIN subjects s ON p.subject_id = s.id
        LEFT JOIN classes  c ON p.class_id  = c.id
        WHERE p.teacher_id=%s AND p.timetable_version=%s
        ORDER BY p.day, p.slot_number
    """, (teacher_id, ver))
    return [dict(r) for r in cur.fetchall()]


def get_all_periods(version=None):
    conn = get_conn()
    cur  = _cur(conn)
    ver  = version or get_active_version()
    cur.execute("""
        SELECT p.*,
               s.name AS subject_name, s.color_hex,
               t.name AS teacher_name,
               c.name AS class_name, c.arm, c.level
        FROM periods p
        LEFT JOIN subjects s ON p.subject_id = s.id
        LEFT JOIN teachers t ON p.teacher_id = t.id
        LEFT JOIN classes  c ON p.class_id   = c.id
        WHERE p.timetable_version=%s
        ORDER BY c.level, c.name, c.arm, p.day, p.slot_number
    """, (ver,))
    return [dict(r) for r in cur.fetchall()]


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════════════════
def count_teacher_periods_per_week(teacher_id, version=None):
    conn = get_conn()
    cur  = _cur(conn)
    ver  = version or get_active_version()
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM periods WHERE teacher_id=%s AND timetable_version=%s",
        (teacher_id, ver)
    )
    row = cur.fetchone()
    return row["cnt"] if row else 0


def get_dashboard_stats(version=None):
    conn = get_conn()
    cur  = _cur(conn)
    ver  = version or get_active_version()

    def scalar(sql, params=()):
        # Alias the aggregate so both Postgres ("count") and SQLite ("COUNT(*)")
        # return the value under the same key.
        cur.execute(sql, params)
        row = cur.fetchone() or {}
        # row may be a dict; pick the only value
        if not row:
            return 0
        return list(row.values())[0]

    stats = {
        "teachers":         scalar("SELECT COUNT(*) AS n FROM teachers"),
        "subjects":         scalar("SELECT COUNT(*) AS n FROM subjects"),
        "classes":          scalar("SELECT COUNT(*) AS n FROM classes"),
        "versions":         scalar("SELECT COUNT(*) AS n FROM timetable_versions"),
        "periods_assigned": scalar(
            "SELECT COUNT(*) AS n FROM periods "
            "WHERE subject_id IS NOT NULL AND timetable_version=%s", (ver,)
        ),
        "periods_total":    scalar(
            "SELECT COUNT(*) AS n FROM periods WHERE timetable_version=%s", (ver,)
        ),
    }
    return stats


# ══════════════════════════════════════════════════════════════════════════════
# Change Log
# ══════════════════════════════════════════════════════════════════════════════
def log_change(action, entity, description, entity_id=None, changed_by="admin"):
    """Append an audit entry. Non-blocking — swallows errors to never break UI."""
    try:
        conn = get_conn()
        cur  = _cur(conn)
        cur.execute("""
            INSERT INTO change_log (action, entity, entity_id, description, changed_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (action, entity, entity_id, description, changed_by))
        conn.commit()
    except Exception as e:
        print(f"[db] ⚠️  log_change failed: {e}")


def get_change_log(limit=100):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        SELECT * FROM change_log
        ORDER BY created_at DESC LIMIT %s
    """, (limit,))
    return [dict(r) for r in cur.fetchall()]


def clear_change_log():
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM change_log")
    conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# Substitutions
# ══════════════════════════════════════════════════════════════════════════════
def add_substitution(absence_date, absent_teacher_id, class_id, subject_id,
                     slot_number, day, substitute_teacher_id=None,
                     reason="", version="v1"):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO substitutions
            (absence_date, absent_teacher_id, substitute_teacher_id,
             class_id, subject_id, slot_number, day, reason, timetable_version)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (absence_date, absent_teacher_id, substitute_teacher_id,
          class_id, subject_id, slot_number, day, reason, version))
    sid = cur.fetchone()["id"]
    conn.commit()
    log_change("CREATE", "substitution", f"Absence on {absence_date} — {day} slot {slot_number}", sid)
    return sid


def get_substitutions(date_filter=None, version=None):
    conn = get_conn()
    cur  = _cur(conn)
    ver  = version or get_active_version()
    if date_filter:
        cur.execute("""
            SELECT s.*,
                   ta.name AS absent_teacher_name,
                   ts.name AS substitute_teacher_name,
                   c.name  AS class_name, c.arm,
                   sub.name AS subject_name
            FROM substitutions s
            LEFT JOIN teachers ta  ON s.absent_teacher_id     = ta.id
            LEFT JOIN teachers ts  ON s.substitute_teacher_id = ts.id
            LEFT JOIN classes  c   ON s.class_id              = c.id
            LEFT JOIN subjects sub ON s.subject_id            = sub.id
            WHERE s.absence_date = %s AND s.timetable_version = %s
            ORDER BY s.slot_number
        """, (date_filter, ver))
    else:
        cur.execute("""
            SELECT s.*,
                   ta.name AS absent_teacher_name,
                   ts.name AS substitute_teacher_name,
                   c.name  AS class_name, c.arm,
                   sub.name AS subject_name
            FROM substitutions s
            LEFT JOIN teachers ta  ON s.absent_teacher_id     = ta.id
            LEFT JOIN teachers ts  ON s.substitute_teacher_id = ts.id
            LEFT JOIN classes  c   ON s.class_id              = c.id
            LEFT JOIN subjects sub ON s.subject_id            = sub.id
            WHERE s.timetable_version = %s
            ORDER BY s.absence_date DESC, s.slot_number
        """, (ver,))
    return [dict(r) for r in cur.fetchall()]


def update_substitution_status(sub_id, status, substitute_teacher_id=None):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        UPDATE substitutions
        SET status=%s, substitute_teacher_id=%s
        WHERE id=%s
    """, (status, substitute_teacher_id, sub_id))
    conn.commit()
    log_change("UPDATE", "substitution", f"Status → {status}", sub_id)


def delete_substitution(sub_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM substitutions WHERE id=%s", (sub_id,))
    conn.commit()
    log_change("DELETE", "substitution", f"Substitution ID={sub_id} removed")


def get_available_substitutes(day, slot_number, version=None):
    """
    Return teachers who are free at a given (day, slot) —
    i.e. not already teaching any class at that slot in the active timetable.
    """
    conn = get_conn()
    cur  = _cur(conn)
    ver  = version or get_active_version()
    cur.execute("""
        SELECT DISTINCT t.id, t.name, t.staff_type, t.available_days
        FROM teachers t
        WHERE t.id NOT IN (
            SELECT p.teacher_id FROM periods p
            WHERE p.day = %s AND p.slot_number = %s
              AND p.timetable_version = %s
              AND p.teacher_id IS NOT NULL
        )
        ORDER BY t.name
    """, (day, slot_number, ver))
    rows = [dict(r) for r in cur.fetchall()]
    # Also filter out parttime teachers not available on this day
    return [
        r for r in rows
        if r["staff_type"] == "fulltime"
        or day in r["available_days"].split(",")
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Notices
# ══════════════════════════════════════════════════════════════════════════════
def add_notice(title, body, class_id=None, subject_id=None,
               priority="normal", expires_on=None):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO notices (title, body, class_id, subject_id, priority, expires_on)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
    """, (title, body, class_id, subject_id, priority, expires_on))
    nid = cur.fetchone()["id"]
    conn.commit()
    log_change("CREATE", "notice", f"Notice: {title}", nid)
    return nid


def get_notices(class_id=None, include_expired=False):
    conn = get_conn()
    cur  = _cur(conn)
    from datetime import date
    today = date.today().isoformat()
    if class_id:
        cur.execute("""
            SELECT n.*, c.name AS class_name, c.arm, s.name AS subject_name
            FROM notices n
            LEFT JOIN classes  c ON n.class_id  = c.id
            LEFT JOIN subjects s ON n.subject_id = s.id
            WHERE (n.class_id = %s OR n.class_id IS NULL)
              AND (%s OR n.expires_on IS NULL OR n.expires_on >= %s)
            ORDER BY
              CASE n.priority
                WHEN 'urgent' THEN 1 WHEN 'high' THEN 2
                WHEN 'normal' THEN 3 ELSE 4 END,
              n.created_at DESC
        """, (class_id, include_expired, today))
    else:
        cur.execute("""
            SELECT n.*, c.name AS class_name, c.arm, s.name AS subject_name
            FROM notices n
            LEFT JOIN classes  c ON n.class_id  = c.id
            LEFT JOIN subjects s ON n.subject_id = s.id
            WHERE (%s OR n.expires_on IS NULL OR n.expires_on >= %s)
            ORDER BY
              CASE n.priority
                WHEN 'urgent' THEN 1 WHEN 'high' THEN 2
                WHEN 'normal' THEN 3 ELSE 4 END,
              n.created_at DESC
        """, (include_expired, today))
    return [dict(r) for r in cur.fetchall()]


def delete_notice(notice_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM notices WHERE id=%s", (notice_id,))
    conn.commit()
    log_change("DELETE", "notice", f"Notice ID={notice_id} deleted")


# ══════════════════════════════════════════════════════════════════════════════
# Clash Detector
# ══════════════════════════════════════════════════════════════════════════════
def detect_clashes(version=None):
    """
    Scan the periods table for constraint violations. Returns list of clash dicts.
    Checks:
      C1 — Teacher double-booked at same (day, slot)
      C2 — Class has two subjects at same (day, slot)
      C3 — Subject under-scheduled vs periods_per_week target
    """
    conn = get_conn()
    cur  = _cur(conn)
    ver  = version or get_active_version()
    clashes = []

    # C1: teacher double-booked
    cur.execute("""
        SELECT p.day, p.slot_number, t.name AS teacher_name,
               COUNT(*) AS cnt
        FROM periods p
        JOIN teachers t ON p.teacher_id = t.id
        WHERE p.timetable_version = %s AND p.teacher_id IS NOT NULL
        GROUP BY p.day, p.slot_number, p.teacher_id, t.name
        HAVING COUNT(*) > 1
    """, (ver,))
    for row in cur.fetchall():
        clashes.append({
            "type": "C1 — Teacher Double-Booked",
            "detail": f"{row['teacher_name']} is assigned to {row['cnt']} classes "
                      f"on {row['day']} slot {row['slot_number']}",
            "severity": "high"
        })

    # C2: class double-booked
    cur.execute("""
        SELECT p.day, p.slot_number, c.name AS class_name, c.arm,
               COUNT(*) AS cnt
        FROM periods p
        JOIN classes c ON p.class_id = c.id
        WHERE p.timetable_version = %s AND p.subject_id IS NOT NULL
        GROUP BY p.day, p.slot_number, p.class_id, c.name, c.arm
        HAVING COUNT(*) > 1
    """, (ver,))
    for row in cur.fetchall():
        clashes.append({
            "type": "C2 — Class Double-Booked",
            "detail": f"{row['class_name']} {row['arm']} has {row['cnt']} subjects "
                      f"on {row['day']} slot {row['slot_number']}",
            "severity": "high"
        })

    # C3: under-scheduled subjects (per class)
    cur.execute("""
        SELECT c.name AS class_name, c.arm, s.name AS subject_name,
               s.periods_per_week AS required,
               COUNT(p.id) AS assigned
        FROM class_subjects cs
        JOIN classes  c ON cs.class_id  = c.id
        JOIN subjects s ON cs.subject_id = s.id
        LEFT JOIN periods p
               ON p.class_id = c.id AND p.subject_id = s.id
              AND p.timetable_version = %s
        GROUP BY c.id, c.name, c.arm, s.id, s.name, s.periods_per_week
        HAVING COUNT(p.id) < s.periods_per_week
    """, (ver,))
    for row in cur.fetchall():
        clashes.append({
            "type": "C3 — Under-Scheduled",
            "detail": f"{row['class_name']} {row['arm']} — {row['subject_name']}: "
                      f"{row['assigned']}/{row['required']} periods assigned",
            "severity": "medium"
        })

    return clashes


# ══════════════════════════════════════════════════════════════════════════════
# Bulk Period Swap
# ══════════════════════════════════════════════════════════════════════════════
def swap_periods(class_id, day_a, slot_a, day_b, slot_b, version=None):
    """
    Swap two period slots for a given class within a timetable version.
    Returns (success: bool, message: str).
    """
    conn = get_conn()
    cur  = _cur(conn)
    ver  = version or get_active_version()

    cur.execute("""
        SELECT * FROM periods
        WHERE class_id=%s AND timetable_version=%s
          AND day=%s AND slot_number=%s
    """, (class_id, ver, day_a, slot_a))
    period_a = cur.fetchone()

    cur.execute("""
        SELECT * FROM periods
        WHERE class_id=%s AND timetable_version=%s
          AND day=%s AND slot_number=%s
    """, (class_id, ver, day_b, slot_b))
    period_b = cur.fetchone()

    if not period_a and not period_b:
        return False, "Both slots are empty — nothing to swap."

    # Check teacher availability for the swap
    if period_a and period_a["teacher_id"]:
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM periods
            WHERE teacher_id=%s AND day=%s AND slot_number=%s
              AND timetable_version=%s AND class_id != %s
        """, (period_a["teacher_id"], day_b, slot_b, ver, class_id))
        if cur.fetchone()["cnt"] > 0:
            cur.execute("SELECT name FROM teachers WHERE id=%s", (period_a["teacher_id"],))
            tname = cur.fetchone()["name"]
            return False, f"Cannot swap: {tname} is already teaching another class on {day_b} slot {slot_b}."

    if period_b and period_b["teacher_id"]:
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM periods
            WHERE teacher_id=%s AND day=%s AND slot_number=%s
              AND timetable_version=%s AND class_id != %s
        """, (period_b["teacher_id"], day_a, slot_a, ver, class_id))
        if cur.fetchone()["cnt"] > 0:
            cur.execute("SELECT name FROM teachers WHERE id=%s", (period_b["teacher_id"],))
            tname = cur.fetchone()["name"]
            return False, f"Cannot swap: {tname} is already teaching another class on {day_a} slot {slot_a}."

    # Perform swap by temporarily nulling one slot
    sub_a = period_a["subject_id"] if period_a else None
    tea_a = period_a["teacher_id"] if period_a else None
    sub_b = period_b["subject_id"] if period_b else None
    tea_b = period_b["teacher_id"] if period_b else None

    cur.execute("""
        UPDATE periods SET subject_id=%s, teacher_id=%s
        WHERE class_id=%s AND timetable_version=%s AND day=%s AND slot_number=%s
    """, (sub_b, tea_b, class_id, ver, day_a, slot_a))

    cur.execute("""
        UPDATE periods SET subject_id=%s, teacher_id=%s
        WHERE class_id=%s AND timetable_version=%s AND day=%s AND slot_number=%s
    """, (sub_a, tea_a, class_id, ver, day_b, slot_b))

    conn.commit()
    log_change("SWAP", "period",
               f"Class {class_id}: swapped {day_a}/slot{slot_a} ↔ {day_b}/slot{slot_b} [{ver}]",
               class_id)
    return True, f"✅ Swapped {day_a} slot {slot_a} ↔ {day_b} slot {slot_b} successfully."


# ══════════════════════════════════════════════════════════════════════════════
# Subject Distribution Analytics
# ══════════════════════════════════════════════════════════════════════════════
def get_subject_distribution(version=None):
    """
    Returns list of {subject_name, total_periods, classes_count, teachers}
    for analytics and the stats report.
    """
    conn = get_conn()
    cur  = _cur(conn)
    ver  = version or get_active_version()
    cur.execute("""
        SELECT s.name AS subject_name,
               COUNT(p.id)               AS total_periods,
               COUNT(DISTINCT p.class_id) AS classes_count,
               t.name                    AS teacher_name
        FROM subjects s
        LEFT JOIN periods  p ON p.subject_id = s.id AND p.timetable_version = %s
        LEFT JOIN teachers t ON s.assigned_teacher_id = t.id
        GROUP BY s.id, s.name, t.name
        ORDER BY total_periods DESC
    """, (ver,))
    return [dict(r) for r in cur.fetchall()]


def get_teacher_availability_matrix():
    """
    Returns {teacher_name: {day: [slot1, slot2, ...]}} of FREE slots.
    Used for the availability calendar view.
    """
    conn = get_conn()
    cur  = _cur(conn)
    ver  = get_active_version()
    ppd  = int(get_config("periods_per_day", 8))
    days = get_config("school_days",
                      "Monday,Tuesday,Wednesday,Thursday,Friday").split(",")

    # Get all assigned (teacher_id, day, slot)
    cur.execute("""
        SELECT teacher_id, day, slot_number FROM periods
        WHERE timetable_version=%s AND teacher_id IS NOT NULL
    """, (ver,))
    busy = set((r["teacher_id"], r["day"], r["slot_number"]) for r in cur.fetchall())

    teachers = get_all_teachers()
    matrix = {}
    for t in teachers:
        avail_days = set(t["available_days"].split(","))
        matrix[t["name"]] = {}
        for day in days:
            if t["staff_type"] == "parttime" and day not in avail_days:
                matrix[t["name"]][day] = []
            else:
                matrix[t["name"]][day] = [
                    s for s in range(1, ppd + 1)
                    if (t["id"], day, s) not in busy
                ]
    return matrix


# ══════════════════════════════════════════════════════════════════════════════
# v5 — NEW TABLES (appended to init_db via migration helper)
# ══════════════════════════════════════════════════════════════════════════════
def migrate_v5():
    """
    Idempotent migration for v5 tables.
    Called by seed_on_cold_start() after init_db().
    Safe to run on existing databases — uses CREATE TABLE IF NOT EXISTS.
    """
    conn = get_conn()
    cur  = _cur(conn)

    # ── Students ──────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id           SERIAL PRIMARY KEY,
            first_name   TEXT NOT NULL,
            last_name    TEXT NOT NULL,
            roll_number  TEXT NOT NULL,
            class_id     INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            gender       TEXT DEFAULT 'M' CHECK(gender IN ('M','F')),
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(roll_number, class_id)
        )
    """)

    # ── Exam Timetable ────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exam_slots (
            id              SERIAL PRIMARY KEY,
            exam_date       TEXT NOT NULL,
            start_time      TEXT NOT NULL,
            end_time        TEXT NOT NULL,
            subject_id      INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
            class_id        INTEGER REFERENCES classes(id) ON DELETE CASCADE,
            venue           TEXT DEFAULT '',
            invigilator_id  INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
            notes           TEXT DEFAULT '',
            session         TEXT DEFAULT '2024/2025',
            term            TEXT DEFAULT 'First Term',
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(exam_date, start_time, class_id)
        )
    """)

    # ── Term Calendar Events ──────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id          SERIAL PRIMARY KEY,
            event_date  TEXT NOT NULL,
            title       TEXT NOT NULL,
            event_type  TEXT DEFAULT 'event'
                            CHECK(event_type IN ('holiday','event','exam','closure')),
            description TEXT DEFAULT '',
            all_classes BOOLEAN DEFAULT TRUE,
            class_id    INTEGER REFERENCES classes(id) ON DELETE SET NULL,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ── Timetable Lock ────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS version_locks (
            id          SERIAL PRIMARY KEY,
            version_tag TEXT NOT NULL UNIQUE,
            locked_at   TIMESTAMPTZ DEFAULT NOW(),
            locked_by   TEXT DEFAULT 'admin',
            reason      TEXT DEFAULT ''
        )
    """)

    # ── School Branding ───────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS school_branding (
            id         SERIAL PRIMARY KEY,
            key        TEXT NOT NULL UNIQUE,
            value      TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    conn.commit()
    global _MIGRATION_LOGGED
    if not _MIGRATION_LOGGED:
        print("[db] ✅ v5 migration complete — students, exam_slots, calendar_events, locks, branding")
        _MIGRATION_LOGGED = True


# ══════════════════════════════════════════════════════════════════════════════
# Students
# ══════════════════════════════════════════════════════════════════════════════
def add_student(first_name, last_name, roll_number, class_id, gender="M"):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO students (first_name, last_name, roll_number, class_id, gender)
        VALUES (%s,%s,%s,%s,%s) RETURNING id
    """, (first_name, last_name, roll_number, class_id, gender))
    sid = cur.fetchone()["id"]
    conn.commit()
    return sid


def get_students_for_class(class_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        SELECT s.*, c.name AS class_name, c.arm
        FROM students s
        JOIN classes c ON s.class_id = c.id
        WHERE s.class_id = %s
        ORDER BY s.roll_number
    """, (class_id,))
    return [dict(r) for r in cur.fetchall()]


def get_all_students():
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        SELECT s.*, c.name AS class_name, c.arm, c.level
        FROM students s
        JOIN classes c ON s.class_id = c.id
        ORDER BY c.level, c.name, c.arm, s.roll_number
    """)
    return [dict(r) for r in cur.fetchall()]


def update_student(student_id, first_name, last_name, roll_number, class_id, gender):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        UPDATE students SET first_name=%s, last_name=%s, roll_number=%s,
               class_id=%s, gender=%s WHERE id=%s
    """, (first_name, last_name, roll_number, class_id, gender, student_id))
    conn.commit()


def delete_student(student_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM students WHERE id=%s", (student_id,))
    conn.commit()


def bulk_add_students(rows, class_id):
    """
    rows: list of dicts with keys first_name, last_name, roll_number, gender
    Returns (added, skipped) counts.
    """
    conn = get_conn()
    cur  = _cur(conn)
    added = skipped = 0
    for r in rows:
        try:
            cur.execute("""
                INSERT INTO students (first_name, last_name, roll_number, class_id, gender)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (roll_number, class_id) DO NOTHING
            """, (r.get("first_name",""), r.get("last_name",""),
                  r.get("roll_number",""), class_id, r.get("gender","M")))
            if cur.rowcount > 0:
                added += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
    conn.commit()
    return added, skipped


def get_class_size_stats():
    """Returns list of {class_name, arm, level, student_count}."""
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        SELECT c.name AS class_name, c.arm, c.level,
               COUNT(s.id) AS student_count
        FROM classes c
        LEFT JOIN students s ON s.class_id = c.id
        GROUP BY c.id, c.name, c.arm, c.level
        ORDER BY c.level, c.name, c.arm
    """)
    return [dict(r) for r in cur.fetchall()]


# ══════════════════════════════════════════════════════════════════════════════
# Exam Timetable
# ══════════════════════════════════════════════════════════════════════════════
def add_exam_slot(exam_date, start_time, end_time, subject_id, class_id,
                  venue="", invigilator_id=None, notes="",
                  session="2024/2025", term="First Term"):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO exam_slots
            (exam_date, start_time, end_time, subject_id, class_id,
             venue, invigilator_id, notes, session, term)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (exam_date, start_time, end_time, subject_id, class_id,
          venue, invigilator_id, notes, session, term))
    eid = cur.fetchone()["id"]
    conn.commit()
    log_change("CREATE", "exam_slot",
               f"Exam: {exam_date} {start_time} class_id={class_id}", eid)
    return eid


def get_exam_slots(session=None, term=None):
    conn = get_conn()
    cur  = _cur(conn)
    filters = []
    params  = []
    if session:
        filters.append("e.session=%s"); params.append(session)
    if term:
        filters.append("e.term=%s"); params.append(term)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    cur.execute(f"""
        SELECT e.*,
               s.name  AS subject_name, s.color_hex,
               c.name  AS class_name, c.arm, c.level,
               t.name  AS invigilator_name
        FROM exam_slots e
        LEFT JOIN subjects s ON e.subject_id    = s.id
        LEFT JOIN classes  c ON e.class_id      = c.id
        LEFT JOIN teachers t ON e.invigilator_id = t.id
        {where}
        ORDER BY e.exam_date, e.start_time, c.name, c.arm
    """, params)
    return [dict(r) for r in cur.fetchall()]


def delete_exam_slot(exam_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM exam_slots WHERE id=%s", (exam_id,))
    conn.commit()
    log_change("DELETE", "exam_slot", f"Exam slot ID={exam_id} deleted")


def get_exam_clash_report(session=None, term=None):
    """
    Returns clashes where the same invigilator or venue is double-booked
    at the same (exam_date, start_time).
    """
    conn = get_conn()
    cur  = _cur(conn)
    clashes = []
    s = session or get_config("current_session", "2024/2025")
    t = term    or get_config("current_term",    "First Term")

    # Invigilator clash
    cur.execute("""
        SELECT e.exam_date, e.start_time, t.name AS invigilator_name,
               COUNT(*) AS cnt
        FROM exam_slots e
        JOIN teachers t ON e.invigilator_id = t.id
        WHERE e.session=%s AND e.term=%s
          AND e.invigilator_id IS NOT NULL
        GROUP BY e.exam_date, e.start_time, e.invigilator_id, t.name
        HAVING COUNT(*) > 1
    """, (s, t))
    for r in cur.fetchall():
        clashes.append({
            "type":   "Invigilator Double-Booked",
            "detail": f"{r['invigilator_name']} at {r['exam_date']} {r['start_time']} "
                      f"({r['cnt']} exams)",
            "severity": "high"
        })

    # Venue clash
    cur.execute("""
        SELECT e.exam_date, e.start_time, e.venue, COUNT(*) AS cnt
        FROM exam_slots e
        WHERE e.session=%s AND e.term=%s
          AND e.venue != ''
        GROUP BY e.exam_date, e.start_time, e.venue
        HAVING COUNT(*) > 1
    """, (s, t))
    for r in cur.fetchall():
        clashes.append({
            "type":   "Venue Double-Booked",
            "detail": f"Venue '{r['venue']}' at {r['exam_date']} {r['start_time']} "
                      f"({r['cnt']} exams)",
            "severity": "high"
        })
    return clashes


# ══════════════════════════════════════════════════════════════════════════════
# Term Calendar
# ══════════════════════════════════════════════════════════════════════════════
def add_calendar_event(event_date, title, event_type="event",
                       description="", all_classes=True, class_id=None):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO calendar_events
            (event_date, title, event_type, description, all_classes, class_id)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
    """, (event_date, title, event_type, description, all_classes, class_id))
    eid = cur.fetchone()["id"]
    conn.commit()
    log_change("CREATE", "calendar_event", f"{event_type}: {title} on {event_date}", eid)
    return eid


def get_calendar_events(month=None, year=None):
    conn = get_conn()
    cur  = _cur(conn)
    if month and year:
        prefix = f"{year}-{month:02d}"
        cur.execute("""
            SELECT e.*, c.name AS class_name, c.arm
            FROM calendar_events e
            LEFT JOIN classes c ON e.class_id = c.id
            WHERE e.event_date LIKE %s
            ORDER BY e.event_date
        """, (f"{prefix}%",))
    else:
        cur.execute("""
            SELECT e.*, c.name AS class_name, c.arm
            FROM calendar_events e
            LEFT JOIN classes c ON e.class_id = c.id
            ORDER BY e.event_date
        """)
    return [dict(r) for r in cur.fetchall()]


def delete_calendar_event(event_id):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM calendar_events WHERE id=%s", (event_id,))
    conn.commit()


def get_holiday_dates():
    """Returns set of date strings that are holidays/closures — used by scheduler."""
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        SELECT event_date FROM calendar_events
        WHERE event_type IN ('holiday','closure')
    """)
    return {r["event_date"] for r in cur.fetchall()}


# ══════════════════════════════════════════════════════════════════════════════
# Timetable Lock
# ══════════════════════════════════════════════════════════════════════════════
def lock_version(version_tag, reason="", locked_by="admin"):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO version_locks (version_tag, locked_by, reason)
        VALUES (%s,%s,%s)
        ON CONFLICT (version_tag) DO NOTHING
    """, (version_tag, locked_by, reason))
    conn.commit()
    log_change("LOCK", "version", f"Locked: {version_tag} — {reason}")


def unlock_version(version_tag):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("DELETE FROM version_locks WHERE version_tag=%s", (version_tag,))
    conn.commit()
    log_change("UNLOCK", "version", f"Unlocked: {version_tag}")


def is_version_locked(version_tag):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT id FROM version_locks WHERE version_tag=%s", (version_tag,))
    return cur.fetchone() is not None


def get_all_locks():
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT * FROM version_locks ORDER BY locked_at DESC")
    return [dict(r) for r in cur.fetchall()]


# ══════════════════════════════════════════════════════════════════════════════
# School Branding
# ══════════════════════════════════════════════════════════════════════════════
def set_branding(key, value):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("""
        INSERT INTO school_branding (key, value)
        VALUES (%s,%s)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
    """, (key, value))
    conn.commit()


def get_branding(key, default=""):
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT value FROM school_branding WHERE key=%s", (key,))
    row = cur.fetchone()
    return row["value"] if row else default


def get_all_branding():
    conn = get_conn()
    cur  = _cur(conn)
    cur.execute("SELECT key, value FROM school_branding")
    return {r["key"]: r["value"] for r in cur.fetchall()}
