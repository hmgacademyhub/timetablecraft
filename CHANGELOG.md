# Changelog — TimetableCraft

All notable changes to this project will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

---

## [5.2.3] — 2026-06-03 · *"Defensive empty packages.txt"*

### Symptom
Streamlit Cloud deploy kept failing with `E: Unable to locate package #` / `E: Unable to locate package Apt` / `E: Unable to locate package packages` etc. even after v5.2.1 supposedly removed the offending `packages.txt`.

### Root cause
GitHub's *Upload files* UI **never deletes existing files** — it only adds or overwrites by filename. Since v5.2.1's fix was to *remove* `packages.txt` from the repo, the broken file with comments was still living on the GitHub repo from the v5.1 era and Streamlit Cloud kept finding it on every rebuild.

### Fixed
- 🛡️ **Shipped an empty (0-byte) `packages.txt`.** Uploading the new build now *overwrites* the broken file instead of leaving it alone. Streamlit Cloud's `apt-get` step sees no package names → cleanly exits with status 0 → moves on to `pip install`. (Verified locally — `apt-get install` with empty input is a no-op success.)
- 📘 Updated `TROUBLESHOOTING.md` with the "*GitHub Upload Files doesn't delete*" trap.

### Action required
After uploading v5.2.3 to GitHub, no manual delete is needed — the broken `packages.txt` gets overwritten with the empty one automatically.

---

## [5.2.2] — 2026-06-03 · *"Hotfix: 'App in the oven' provisioner stall"*

### Symptom
Streamlit Cloud build stuck at *"Spinning up manager process…"* or *"App in the oven…"* for 10+ minutes, never reaching *"Cloning repository"* or *"Processing dependencies"*.

### Root causes (diagnosed against your real deploy logs)
1. **`psycopg2-binary` in the default `requirements.txt`** added a heavy compiled C extension that the provisioner has to resolve and stage **before** it even shows you the *"Processing dependencies"* log line. On a fully-utilised free-tier provisioner this can stall the build for the full timeout window. Since v5.2 the SQLite backend has been the default — `psycopg2-binary` is no longer needed by default.
2. **Stale `runtime.txt`.** Streamlit Cloud now reads the standard `.python-version` file (the same convention `pyenv` uses). `runtime.txt` is undocumented and frequently ignored, so the platform fell back to its current default (Python 3.14), forcing a heavier dep resolution.
3. **Account-level slug collisions.** Multiple stuck/abandoned apps on the same account can hold provisioning slots and silently block new deploys.

### Fixed
- 📦 **`psycopg2-binary` moved out of `requirements.txt`** into a separate `requirements-postgres.txt`. Default install is now: streamlit, pandas, pulp, reportlab, plotly, openpyxl — all pure-Python wheels or with prebuilt cp311 wheels.
- 🐍 **Added `.python-version`** with `3.11` to lock down a fast, stable, well-supported Python build for Streamlit Cloud.
- 🗑️ Removed the deprecated `runtime.txt`.

### Action required from the developer
1. **Delete any old stuck apps** in your Streamlit Cloud dashboard (https://share.streamlit.io) — keep only the one you want to use. Multiple stuck apps on the same account can deadlock provisioning.
2. After uploading this v5.2.2 build, **fully reboot the app** (not just redeploy). Manage app → ⋮ → Reboot.

---

## [5.2.1] — 2026-06-03 · *"Hotfix: Streamlit Cloud apt parser"*

### Fixed
- 🔴 **Streamlit Cloud deployment crash** during `apt-get` phase. Removed `packages.txt` entirely. Streamlit Cloud's `packages.txt` parser splits every line on whitespace and treats every token as a package name — including comment text — so the `# …` lines in the v5.2.0 `packages.txt` were being passed to `apt-get install` as package names ("packages", "Apt", "for", "Streamlit", "Community", "but", "we", "list", "explicitly", …), all of which failed with *"Unable to locate package"* and aborted the build.
- `psycopg2-binary` ships its own `libpq` and SQLite is in Python's stdlib, so no apt-level system packages are actually required. `packages.txt` is now omitted by design.

---

## [5.2.0] — 2026-06-03 · *"Zero-config: SQLite default, Postgres optional"*

### Added
- **Backend-agnostic data layer.** `db.py` now auto-detects and supports both **SQLite** (default, zero config) and **PostgreSQL** (opt-in upgrade).
- Backend auto-selection priority: `TIMETABLECRAFT_DB` env var → `DATABASE_URL` → `st.secrets["postgres"]` → `st.secrets["supabase"]` (back-compat) → `PG*` env vars → SQLite fallback.
- `[postgres]` is the new canonical secrets section name; `[supabase]` still works for back-compat.
- New env-var entry point: `DATABASE_URL=postgresql://…` (works on Render, Railway, Heroku, Fly.io out of the box).
- SQLite path knobs: `TIMETABLECRAFT_DB_PATH` to set the file location.
- **Sidebar backend badge** (📦 SQLite / 🐘 Postgres) so admins see at a glance which DB is active.
- `get_backend()` and `backend_summary()` helpers exported from `db.py`.
- `_DictRowCursor` wrapper that makes SQLite cursors look identical to psycopg2's `RealDictCursor`.
- On-the-fly SQL dialect translator (`SERIAL`, `TIMESTAMPTZ`, `BOOLEAN`, `NOW()`, `%s` → SQLite equivalents).
- WAL journal mode + `PRAGMA foreign_keys=ON` for the SQLite backend.

### Changed
- `psycopg2-binary` is now **optional** — only required if you opt into the Postgres backend. If you stay on SQLite you can delete the line from `requirements.txt` and save ~5 MB from your Cloud build.
- Bootstrap error card is now **backend-aware** — gives different remedies for SQLite (file permissions, write paths) vs Postgres (secrets, paused project, firewall).
- `get_dashboard_stats()` uses index-based scalar reads to be portable across both backends (PG names the unnamed `COUNT(*)` column `count`, SQLite names it `COUNT(*)`).
- `README.md` quickstart is now **`pip install && streamlit run`** — no DB account required.
- `DEPLOYMENT.md` reorganised around **Path A — Zero-config (SQLite)** and **Path B — Hosted Postgres**.
- `secrets.toml.template` rewritten to clarify that the file is **optional**.
- Default install removes the live-site outage class entirely: blank-screen failures could only happen if the user explicitly opted into Postgres and got the secret wrong.

### Fixed
- `get_dashboard_stats()` `KeyError: 'count'` on SQLite — now reads scalar by index.

---

## [5.1.0] — 2026-06-03 · *"HMG-branded production rebuild"*

### Added
- `branding.py` — single source of truth for every brand string, link, colour, and HTML helper used across the UI.
- HMG-branded sidebar header, sidebar footer, dashboard *About* card, and a global footer visible on every page.
- HMG-branded two-line attribution footer on **every PDF page** generated.
- `menu_items` (About / Help / Report a bug) wired into `st.set_page_config`.
- `assets/hmg_logo.png` and `assets/timetablecraft_banner.png` shipped with the repo.
- `DEPLOYMENT.md` — full step-by-step Supabase + Streamlit Cloud guide.
- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`.
- `.streamlit/config.toml` — HMG palette as the default theme.
- `.streamlit/secrets.toml.template` — properly-named template (the old `.txt` is still kept for back-compat).
- Environment-variable fallback for DB credentials (`PGHOST` / `PGDATABASE` / `PGUSER` / `PGPASSWORD` / `PGSSLMODE`) — no more hard dependency on `st.secrets`.
- `_smoketest.py` — `streamlit.testing.v1.AppTest` harness that drives all 20 pages and asserts zero exceptions.

### Changed
- Default school name is now **"HMG Academy"** (was *"TimetableCraft Academy"*).
- Demo seeder now seeds *"HMG Academy Demo"* instead of *"Greenfield Academy"*.
- `app.py` now calls `st.set_page_config()` **before** the DB bootstrap, so credential / connection failures render a clean red error card instead of the blank Streamlit *"status embed"* iframe.
- `db.py` connection pool is now serialised with a `threading.RLock` (multi-user safe).
- `db.py` reconnect path properly `.close()`s dead handles (no more connection leaks).
- `db.py` liveness probe now `rollback()`s — no more idle-in-transaction handles.
- `requirements.txt` pinned with upper bounds (`<2.0`, `<3.0`, …) to prevent silent breakage from upstream major releases.
- All 48 deprecated `use_container_width=True` calls replaced with `width="stretch"`.

### Fixed
- 🔴 **Blank-screen bootstrap crash** on Streamlit Cloud when `[supabase]` secret is missing — root cause of the original `https://hmgacademy-timetablecraft.streamlit.app/` outage.
- 🔴 Thread-unsafe shared psycopg2 connection across sessions.
- 🟠 Leaked psycopg2 connections after Supabase idle-disconnects.
- 🟠 `needs_seeding()` returning `True` on *any* exception, which forced doomed re-seeds on every reload.
- 🟠 First-boot LP solve crashing the script if it overran the 30 s request budget — now caught with a friendly log message; the seed survives.

### Removed
- Repeated `init_db` / `migrate_v5` log lines on every script rerun — now print once per process.

---

## [5.0.0] — 2026-05-05 · *"Full production"*

Initial v5 production release: students, exam timetable, calendar, version locks, branding tables.

---

*Maintained by **Adewale Samson Adeagbo** for **HMG Technologies** (a subsidiary of **HMG Concepts**).*
