# Contributing to TimetableCraft

Thank you for considering a contribution! TimetableCraft is built by **HMG Technologies** (a subsidiary of **HMG Concepts**, est. 2015, Lagos) and is designed to serve **HMG Academy** and partner Nigerian schools. Your help keeps it sharp.

> *“Learning Deliberately. Teaching Authentically.”*

---

## How to contribute

### 1. Open an issue first

For anything bigger than a typo, please [open an issue](https://github.com/cssadewale/timetablecraft/issues/new) and describe:

- What you intend to change
- Why it's needed (real classroom problem, ideally)
- Any UI screenshots / mockups

This avoids you doing work that won't be merged.

### 2. Fork → branch → PR

```bash
git checkout -b feat/short-feature-name
# …make changes…
python _smoketest.py     # must pass with 20/20 ✅ before you push
git commit -m "feat(scope): short description"
git push origin feat/short-feature-name
```

Then open a Pull Request against `main`.

---

## Coding standards

- **Python ≥ 3.10**, formatted with `black -l 100`.
- **Type hints** on every new function signature.
- **Docstrings** for every public function (Google style).
- **No raw SQL outside `db.py`.** All persistence must go through a `db.py` helper.
- **No hard-coded brand strings** outside `branding.py`. If you need a new colour / URL / brand line, add it to `branding.py` and import it.
- **No new `use_container_width=` calls** — use `width="stretch"` or `width="content"`.
- **Always pass the active version** explicitly to scheduler / period queries. Don't rely on global state.
- **PDFs must keep the HMG attribution footer.** It is the legal trade-off for the MIT licence; don't strip it.

---

## Project layout

```
.
├── app.py              # Streamlit UI — single-file 20-page router
├── branding.py         # HMG brand constants + HTML helpers
├── db.py               # Postgres data layer (psycopg2)
├── scheduler.py        # Greedy + PuLP solver
├── pdf_gen.py          # ReportLab PDF / CSV exporters
├── startup.py          # Idempotent cold-start seeder
├── _smoketest.py       # AppTest end-to-end harness
├── requirements.txt
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.template
├── assets/             # Brand artwork (logo, banner)
├── README.md
├── DEPLOYMENT.md
├── CONTRIBUTING.md
├── CHANGELOG.md
└── LICENSE             # MIT + HMG attribution clause
```

---

## Testing

```bash
# Headless test of every page:
python _smoketest.py

# Manual:
streamlit run app.py
```

All 20 pages must render without an exception before a PR is mergeable.

---

## Commit message convention

`<type>(<scope>): <summary>`

| Type | Used for |
|------|----------|
| `feat` | New user-visible feature |
| `fix` | Bug fix |
| `perf` | Performance improvement |
| `refactor` | Internal change with no user-visible effect |
| `docs` | Docs only |
| `style` | Formatting only |
| `test` | Tests only |
| `chore` | Build, deps, tooling |

Examples:

```
feat(scheduler): support 6-day week with Saturday clubs
fix(db): close dead psycopg2 handle on idle-disconnect reconnect
docs(deployment): add Hugging Face Spaces alternative host
```

---

## Code of conduct

Be kind, be patient, assume good intent. See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

---

## Reaching the maintainer

| Channel | Where |
|---------|-------|
| 💻 GitHub issues | https://github.com/cssadewale/timetablecraft/issues |
| 💬 WhatsApp | +234 810 086 6322 |
| 📧 Email | hello@hmgconcepts.com |
| 💼 LinkedIn | https://linkedin.com/in/adewalesamsonadeagbo |
| 🌐 Personal | https://cssadewale.pages.dev |

---

*Maintained by **Adewale Samson Adeagbo**, Founder of **HMG Concepts**.*
