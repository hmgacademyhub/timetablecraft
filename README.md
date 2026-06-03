<div align="center">

<img src="assets/hmg_logo.png" alt="HMG Concepts" width="120"/>

# 📅 TimetableCraft

**Constraint-Aware Timetable Scheduling for African Schools**

*A product of [HMG Technologies](https://hmgconcepts.pages.dev) — the EdTech arm of [HMG Concepts](https://hmgconcepts.pages.dev), built for [HMG Academy](https://hmgacademy.pages.dev) and Nigerian secondary schools.*

[![Built by HMG Technologies](https://img.shields.io/badge/Built%20by-HMG%20Technologies-1A56DB?style=flat-square)](https://hmgconcepts.pages.dev)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)](https://www.python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32%2B-FF4B4B?style=flat-square)](https://streamlit.io)
[![Database](https://img.shields.io/badge/Database-Supabase%20Postgres-3FCF8E?style=flat-square)](https://supabase.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

<img src="assets/timetablecraft_banner.png" alt="TimetableCraft" width="100%"/>

</div>

---

## ✨ What is TimetableCraft?

**TimetableCraft** is a production-grade, web-based school timetable engine designed for Nigerian secondary schools (JSS 1 – SSS 3) and adaptable to any African school structure. It replaces the wall-chart, the spreadsheet, and the “excel-and-pray” workflow that most schools still depend on, with:

- 🚀 **Zero-config install** — works straight out of the box on SQLite, no cloud DB signup required. Upgrade to PostgreSQL only when you need it.
- a **constraint-satisfaction scheduler** (greedy initialisation + PuLP linear-programming conflict resolution),
- per-class **subject mappings**, **double-period** preferences, **break/assembly** awareness,
- a full **operations cockpit** — substitutions, exam timetables, term calendar, notices, change log, branding,
- **version control & locks** so the bursary-approved timetable can never be silently overwritten,
- one-click **PDF / CSV exports** branded with your school name *and* the HMG attribution footer.

> *“Learning Deliberately. Teaching Authentically.”* — the HMG Concepts philosophy that guides every line of code in this project.

---

## 🧠 Why this exists

This tool was built by **[Adewale Samson Adeagbo](https://cssadewale.pages.dev)** — an AI-Augmented Solutions Developer, data scientist, and STEM educator with **15+ years of classroom experience** across Lagos and Ogun State. The problem is one he watched up close, every term, for fifteen years: drafting a workable school timetable by hand consumes a vice-principal’s entire mid-term break and *still* produces clashes.

TimetableCraft solves that, end-to-end, in seconds — and because it is built by an educator, not just an engineer, every page reflects the actual workflow of a real Nigerian school.

---

## 🚀 Features (20 pages, 5 modules)

| Group | Pages |
|-------|-------|
| **Master data** | 👩‍🏫 Teachers · 📚 Subjects · 🏫 Classes · 🗂️ Class-Subjects · 👨‍🎓 Students |
| **Engine** | 🚀 Generate Timetable · 📅 View Timetable · 🔍 Clash Detector |
| **Operations** | 🔄 Substitutions · 📢 Notices · 📝 Exam Timetable · 📅 Term Calendar |
| **Governance** | 📋 Versions · 🔒 Version Lock · 📋 Change Log |
| **Admin & UX** | 🏠 Dashboard · ⚙️ Settings · 🎨 Branding · 📊 Statistics · 📤 Export |

**Engine highlights**

- Greedy initialisation honours per-teacher availability, max periods/week, full/part-time status.
- PuLP linear-programming pass resolves residual clashes.
- Awareness of double periods, assembly, break, Friday short-day timing.
- Multi-version timetables (e.g. `v1`, `v2-rainy-season`, `Term2-Plan`) with one active at a time and admin-lockable.

**Exports**

- Per-class PDF · per-teacher PDF · master CSV/Excel · exam timetable PDF · student register PDF · generation report PDF · statistics PDF.
- Every page carries the school’s name and a *“Powered by TimetableCraft · HMG Technologies”* attribution footer.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Streamlit UI  (app.py)  — 20 pages, single-file router         │
│                  │                                              │
│                  ▼                                              │
│  branding.py  (HMG / TimetableCraft brand constants & HTML)     │
│                                                                 │
│  startup.py  → init_db() · migrate_v5() · idempotent seeder     │
│                                                                 │
│  scheduler.py  Greedy + PuLP LP solver                          │
│                                                                 │
│  pdf_gen.py    ReportLab exports (branded footers)              │
│                                                                 │
│  db.py         psycopg2 ↔ Supabase Postgres                     │
│                  │                                              │
│                  ▼                                              │
│             ┌──────────────────┐                                │
│             │  Supabase / PG   │                                │
│             └──────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

| File | Role |
|------|------|
| `app.py` | Streamlit UI — 20 pages, sidebar router, brand footer |
| `branding.py` | Single source of truth for every brand string, link, colour, HTML snippet |
| `db.py` | Postgres data layer — thread-safe pooled connection, idempotent schema, 50+ helper functions |
| `scheduler.py` | Constraint-satisfaction engine — Greedy + PuLP, exports report data |
| `pdf_gen.py` | ReportLab PDF / CSV generators — all with branded footer |
| `startup.py` | Cold-start orchestrator: `init_db → migrate_v5 → seed (only if empty) → generate v1` |
| `_smoketest.py` | `streamlit.testing.v1.AppTest` harness — drives all 20 pages, asserts zero exceptions |

---

## ⚡ Quick start (local) — zero config

```bash
# 1. Clone
git clone https://github.com/hmgacademyhub/timetablecraft.git
cd timetablecraft

# 2. Create a Python 3.10+ venv & install deps
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Run — that's it.
streamlit run app.py
```

Visit `http://localhost:8501` and the app will:

1. paint the page chrome immediately,
2. create a local **`timetablecraft.db`** SQLite file next to `app.py`,
3. run all schema migrations (idempotent),
4. seed the *HMG Academy Demo* school **only if the DB is empty**,
5. generate a complete timetable into version `v1` on first boot.

No database account. No secrets. No cloud signup. **Just `pip install` and `streamlit run`.**

### Database backends

| Backend | Configuration | Best for |
|---------|---------------|----------|
| 📦 **SQLite** *(default)* | Zero config — single `timetablecraft.db` file | Single-school deployments, demos, local dev |
| 🐘 **PostgreSQL** *(optional)* | `pip install -r requirements-postgres.txt`, then set `[postgres]` in `.streamlit/secrets.toml` or `DATABASE_URL` env var | Multi-user / cloud / hosted (Supabase, Neon, Render, Railway, self-hosted) |

The active backend is auto-detected and shown as a coloured badge in the sidebar.
See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the full backend-selection logic and
[`DATABASES.md`](DATABASES.md) for the technical reference.

> 🐍 **Python:** the repo ships `.python-version` with `3.11`. Stick with this — Streamlit Cloud defaults to a much newer Python that may stall provisioning while it tries to resolve heavier dependency builds.

---

## ☁️ Deploying to Streamlit Community Cloud

See **[`DEPLOYMENT.md`](DEPLOYMENT.md)** for the step-by-step guide. The short version:

1. Push this repo to GitHub.
2. On https://share.streamlit.io → **New app** → point at `main` / `app.py`.
3. In **App settings → Secrets**, paste your `[supabase]` block (see the template).
4. Click **Deploy**.

If the `[supabase]` block is missing or wrong, the app now displays a **clear red error card** with the exact remedy instead of dying with a blank “status embed” screen.

---

## 🧪 Smoke testing

```bash
python _smoketest.py
```

Uses the official `streamlit.testing.v1.AppTest` harness to drive every one of the 20 pages and asserts that no exception is raised on any of them. Add this to your CI to catch regressions before deploy.

---

## 📚 Documentation index

| Document | Purpose |
|----------|---------|
| [`README.md`](README.md) | You are here |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Step-by-step deployment guide (SQLite & Postgres paths) |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | **Read this first if a deploy is stuck or failing** |
| [`DATABASES.md`](DATABASES.md) | How the SQLite ↔ Postgres backend selection works |
| [`CHANGELOG.md`](CHANGELOG.md) | Version history |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Coding standards & PR workflow |
| [`SECURITY.md`](SECURITY.md) | Vulnerability disclosure |
| [`LICENSE`](LICENSE) | MIT, with HMG attribution clause |

---

## 👤 Built by

<table>
<tr>
<td width="120" valign="top">

<img src="https://github.com/cssadewale.png" width="100" alt="Adewale Samson Adeagbo" style="border-radius: 50%"/>

</td>
<td valign="top">

### Adewale Samson Adeagbo

**AI-Augmented Solutions Developer · Data Scientist · STEM Educator**

15+ years in Nigerian classrooms (Nursery → SSS3) · 12 deployed ML & EdTech projects · Founder of HMG Concepts (est. 2015).

- 🌐 Portfolio: [cssadewale.pages.dev](https://cssadewale.pages.dev)
- 🎓 HMG Academy: [hmgacademy.pages.dev](https://hmgacademy.pages.dev)
- 🏢 HMG Concepts: [hmgconcepts.pages.dev](https://hmgconcepts.pages.dev)
- 💼 LinkedIn: [adewalesamsonadeagbo](https://linkedin.com/in/adewalesamsonadeagbo)
- 💻 GitHub: [@cssadewale](https://github.com/cssadewale)
- 🎥 YouTube: [@hmgconcepts](https://youtube.com/@hmgconcepts)
- 💬 WhatsApp: [+234 810 086 6322](https://wa.me/2348100866322)

</td>
</tr>
</table>

---

## 🤝 The HMG Concepts family

| Subsidiary | What it does |
|------------|--------------|
| 🎓 **HMG Academy** | Full virtual learning institution — Nursery to SSS · WAEC/NECO/JAMB/IGCSE/IELTS prep. |
| 💻 **HMG Technologies** | EdTech & data tools — *TimetableCraft, [CBT Pro](https://cssadewale.github.io/cbt-system), and more*. |
| 📢 **HMG Media** | Educational content, digital presence, community engagement. |

---

<div align="center">

*“Learning Deliberately. Teaching Authentically.”*

**TimetableCraft v5.1** — © 2015 – 2026 HMG Concepts · Built with ❤️ in Lagos, Nigeria.

</div>
