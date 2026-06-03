# 🚀 TimetableCraft — Deployment Guide

> *A product of HMG Technologies — the EdTech arm of HMG Concepts.
> Engineered by Adewale Samson Adeagbo · [hmgconcepts.pages.dev](https://hmgconcepts.pages.dev)*

This guide walks you, step by step, from a fresh GitHub repo to a live deployment. It supports **two backends**:

| Backend | Setup | Best for |
|---------|-------|----------|
| 📦 **SQLite** *(default · zero-config)* | Nothing to do — works out of the box | Single-school deployments, demos, local installs |
| 🐘 **PostgreSQL** *(optional)* | Add a `[postgres]` secrets block | Multi-admin / hosted cloud / Supabase / Neon / Render |

---

## Table of contents

1. [Backend selection — how it works](#backend-selection--how-it-works)
2. [Path A — Zero-config (SQLite)](#path-a--zero-config-sqlite)
3. [Path B — Hosted PostgreSQL](#path-b--hosted-postgresql)
4. [Deploying to Streamlit Cloud](#deploying-to-streamlit-cloud)
5. [Day-2 operations](#day-2-operations)
6. [Troubleshooting](#troubleshooting)
7. [Alternative hosts](#alternative-hosts)
8. [Backups & restore](#backups--restore)

---

## Backend selection — how it works

`db.py` auto-detects which backend to use, in this order of priority:

1. Env var `TIMETABLECRAFT_DB=sqlite` *or* `TIMETABLECRAFT_DB=postgres` — explicit override.
2. Env var `DATABASE_URL=postgresql://…` — used by Render, Railway, Heroku, Fly.io.
3. Env var `DATABASE_URL=sqlite:///path/to/file.db`.
4. `st.secrets["postgres"]` block in `.streamlit/secrets.toml` or Streamlit Cloud secrets.
5. `st.secrets["supabase"]` block (back-compat with v5.0.x).
6. `PGHOST` + `PGDATABASE` + `PGUSER` env vars.
7. **Fallback → SQLite** at `./timetablecraft.db` (override path with `TIMETABLECRAFT_DB_PATH`).

A coloured badge in the sidebar (📦 **SQLite** or 🐘 **Postgres**) tells you which backend is active.

---

## Path A — Zero-config (SQLite)

This is the easiest, fastest, and most appropriate setup for **one school with one admin**.

### Local

```bash
git clone https://github.com/hmgacademyhub/timetablecraft.git
cd timetablecraft
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

That's it. A `timetablecraft.db` file appears next to `app.py`. **Back it up the same way you'd back up any important file** — copy it to Dropbox / Google Drive / a USB stick whenever you finish a planning session.

### Streamlit Community Cloud

1. Push the repo to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io) → **New app** → point at `main` / `app.py`.
3. **Leave the Secrets box empty.**
4. Click **Deploy**.

The app boots into the demo school, you log in as an admin (just open the URL), and you can start adding teachers / subjects / classes.

> ⚠️ **Caveat — Streamlit Cloud's filesystem is ephemeral.** Files written to disk inside a Streamlit Cloud app are preserved as long as the container stays warm, but they can be lost when Streamlit redeploys the container (e.g. after a git push, a settings change, or several days of inactivity).
>
> **For a long-lived multi-week timetable that survives redeploys, switch to Path B (hosted Postgres).** For demos, training, and "I want to try this out" use, SQLite on Cloud is perfectly fine.

### Self-hosted (VPS, Docker, home server)

This is where SQLite **shines** — your data lives in one file under your control:

```bash
docker run -d --name timetablecraft \
  -p 8501:8501 \
  -v /opt/timetablecraft:/data \
  -e TIMETABLECRAFT_DB_PATH=/data/timetablecraft.db \
  -w /app -v $(pwd):/app \
  python:3.11-slim \
  bash -c "pip install -r requirements.txt && streamlit run app.py --server.headless=true --server.address=0.0.0.0"
```

Back it up with `cp /opt/timetablecraft/timetablecraft.db /backups/$(date +%F).db`.

---

## Path B — Hosted PostgreSQL

Use this when:

- Multiple admins need to edit the timetable simultaneously, **or**
- You need point-in-time / managed backups, **or**
- You're on Streamlit Cloud and want data to survive container redeploys.

### B-1. Provision the database

Any Postgres works. Recommended free tiers:

| Provider | Notes |
|----------|-------|
| [**Supabase**](https://supabase.com) | Generous free tier · automatic backups · 7-day idle-pause on free plan |
| [**Neon**](https://neon.tech) | Serverless · no idle pause · branchable |
| [**Render**](https://render.com) | 90-day free Postgres · easy URL-based connection |
| [**Railway**](https://railway.app) | Pay-as-you-go · provides `DATABASE_URL` |
| Self-hosted on your VPS | `docker run -d -e POSTGRES_PASSWORD=… postgres:17` |

Get these five values from your provider's connection-info screen:

```
Host:     db.<project-ref>.supabase.co
Database: postgres
Port:     5432
User:     postgres
Password: <generated>
```

### B-2. Configure TimetableCraft

**Option 1 — secrets file (recommended for Streamlit Cloud):**

```toml
# .streamlit/secrets.toml
[postgres]
host     = "db.xxxxxxxxxxxx.supabase.co"
port     = 5432
dbname   = "postgres"
user     = "postgres"
password = "YOUR-DB-PASSWORD"
sslmode  = "require"
```

(`[supabase]` is also accepted, for back-compat with the v5.0.x deployment.)

**Option 2 — `DATABASE_URL` env var (recommended for Render, Railway, Heroku):**

```bash
export DATABASE_URL="postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres?sslmode=require"
```

**Option 3 — individual env vars:**

```bash
export PGHOST=db.xxx.supabase.co PGPORT=5432 PGDATABASE=postgres \
       PGUSER=postgres PGPASSWORD=... PGSSLMODE=require
```

Reload the app. The sidebar badge will switch from 📦 **SQLite** to 🐘 **Postgres**, and all data will now persist in your hosted DB.

---

## Deploying to Streamlit Cloud

(Same steps for SQLite or Postgres — just skip the Secrets step if you're staying on SQLite.)

1. **Push the repo to GitHub:**
   ```bash
   git add -A
   git commit -m "feat: TimetableCraft v5.2"
   git push origin main
   ```
2. Go to [**share.streamlit.io**](https://share.streamlit.io) → **New app**.
3. Pick **Repository:** `your-account/timetablecraft`, **Branch:** `main`, **Main file:** `app.py`.
4. **Advanced settings → Python version:** `3.11` *(critical — see below).*
5. *(Postgres path only)* **Secrets:** paste your `[postgres]` block.
6. *(Postgres path only)* **Append `psycopg2-binary>=2.9.9,<3.0` to `requirements.txt`** *(or copy the line from `requirements-postgres.txt`)*. The default `requirements.txt` deliberately omits it so SQLite-only deployments build faster.
7. Click **Deploy**.

> ⚠️ **Pin Python 3.11 — do not let Streamlit Cloud default to 3.14.**
> The repo ships a `.python-version` file with `3.11` for exactly this
> reason. If you skip the *Advanced settings* step *and* delete
> `.python-version`, the provisioner may stall at *"App in the oven…"*
> while it tries to resolve newer Python builds.

First build takes ~90 s. Watch the logs for:

```
[db] ✅ Schema ready (sqlite) — all tables initialised.
[db] ✅ v5 migration complete — students, exam_slots, calendar_events, locks, branding
[startup] 🌱 Empty database — seeding HMG Academy Demo school…
[scheduler] ✅ Done! 200 periods | … | version=v1
```

…and the app lands on a populated **🏠 HMG Academy Demo Dashboard**.

---

## Day-2 operations

| Task | Where |
|------|-------|
| **Rename the school** | ⚙️ Settings → *School name* |
| **Upload a logo** | 🎨 Branding → *Logo* |
| **Set break / assembly / day-length** | ⚙️ Settings → *General* |
| **Add real teachers / subjects / classes** | 👩‍🏫 Teachers · 📚 Subjects · 🏫 Classes |
| **Map subjects to each class** | 🗂️ Class Subjects |
| **Re-generate the timetable** | 🚀 Generate Timetable |
| **Lock the approved version** | 🔒 Version Lock |
| **Export PDFs** | 📤 Export |
| **Check which backend is active** | Sidebar — coloured badge under the active timetable card |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| **Build stuck at *"App in the oven…"* / *"Spinning up manager…"* for 10+ minutes.** | Streamlit Cloud provisioner stall — usually caused by (a) too many stuck apps on your account holding slots, (b) Python 3.14 + heavy compiled deps, or (c) a corrupted previous deploy. | (1) Go to https://share.streamlit.io → **delete every old/stuck app** for this repo, keep only one. (2) Make sure `.python-version` exists with `3.11`. (3) `psycopg2-binary` must NOT be in `requirements.txt` unless you actually need Postgres. (4) After redeploying, Manage app → ⋮ → **Reboot** (don't just push another commit). |
| **Blank page — only the Streamlit "status embed" iframe is visible.** | Pre-v5.1 bootstrap crash before `set_page_config()`. | Upgrade. v5.1+ paints the page chrome **first** and shows a red error card on failures. |
| **Red card: *"Could not start its database"* (SQLite mode).** | Container filesystem is read-only. | Set `TIMETABLECRAFT_DB_PATH=/tmp/timetablecraft.db` (writable on most platforms). |
| **Red card: *"Could not start its database"* (Postgres mode).** | Wrong secret · paused DB · firewall. | Re-check the `[postgres]` block · un-pause the project · reload. |
| **SQLite data disappears between Streamlit Cloud redeploys.** | Container filesystem is ephemeral. | Move to Path B (hosted Postgres) for persistent storage. |
| **`OperationalError: SSL connection has been closed unexpectedly`.** | Supabase free-tier idle drop. | v5.1+ auto-reconnects. If it still recurs, enable **Connection Pooling** in Supabase. |
| **LP solver timeout on first boot.** | Cloud's 30-s request budget exceeded. | v5.1+ catches this gracefully — open the **🚀 Generate Timetable** page and click Generate. |
| **`use_container_width` deprecation noise in logs.** | Older Streamlit kwarg. | v5.1+ uses `width="stretch"` everywhere. |
| **Two users editing simultaneously gives errors.** | Connection sharing. | v5.1+ added a process-level RLock. For >2 admins, use Postgres (Path B). |
| **Switching backends loses my data.** | They're separate databases. | Export to CSV / PDF first (📤 Export), switch backend, then re-import. |

---

## Alternative hosts

TimetableCraft is just a Streamlit app + optional Postgres. It runs anywhere Python runs:

| Host | Sqlite OK? | Notes |
|------|:----------:|-------|
| **Streamlit Community Cloud** | ✅ | Free tier · ephemeral disk · prefer Postgres for long-lived data |
| **Render** | ✅ | Free Postgres add-on via `DATABASE_URL` |
| **Railway** | ✅ | Same — `DATABASE_URL` auto-injected |
| **Fly.io** | ✅ | Persistent volumes (`fly volumes create`) make SQLite production-grade |
| **Hugging Face Spaces** (Streamlit SDK) | ✅ | Persistent storage available on paid tiers |
| **Self-hosted VPS** | ✅ | `nginx` reverse-proxy + `systemd` service · SQLite is perfect here |

---

## Backups & restore

### SQLite

```bash
# Just copy the file — it's a single-file format.
cp timetablecraft.db backups/timetablecraft_$(date +%F).db

# Restore: stop the app, overwrite, restart.
cp backups/timetablecraft_2026-06-03.db timetablecraft.db
```

Or use SQLite's built-in online backup:

```bash
sqlite3 timetablecraft.db ".backup backups/timetablecraft_$(date +%F).db"
```

### Postgres

Supabase / Neon / Render keep **7+ days of automatic daily backups** on free tiers (longer on paid). To take a manual snapshot:

```bash
pg_dump "postgresql://postgres:PASSWORD@db.<ref>.supabase.co:5432/postgres" \
        --clean --if-exists --no-owner --no-acl \
        -f hmg_timetable_$(date +%F).sql
```

Restore:

```bash
psql  "postgresql://postgres:PASSWORD@db.<ref>.supabase.co:5432/postgres" \
     -f hmg_timetable_2026-06-03.sql
```

---

<div align="center">

*"Learning Deliberately. Teaching Authentically."*
**TimetableCraft v5.2** · Built by **HMG Technologies** for **HMG Academy** and partner schools across Nigeria.

</div>
