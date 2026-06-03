# Security Policy — TimetableCraft

*Maintained by **HMG Technologies** — a subsidiary of **HMG Concepts**.*

---

## Supported versions

| Version | Supported |
|---------|-----------|
| 5.1.x   | ✅ Yes — current production |
| 5.0.x   | ⚠️ Best-effort only |
| < 5.0   | ❌ Unsupported |

---

## Reporting a vulnerability

**Please do not open a public GitHub issue for security reports.**

Instead, contact us privately:

| Channel | How |
|---------|-----|
| 📧 Email | **hello@hmgconcepts.com** *(preferred)* |
| 💬 WhatsApp | [+234 810 086 6322](https://wa.me/2348100866322) |
| 💼 LinkedIn DM | [adewalesamsonadeagbo](https://linkedin.com/in/adewalesamsonadeagbo) |

Include:

1. The version (`branding.PRODUCT_VERSION`) you tested against
2. Reproduction steps
3. Expected vs actual behaviour
4. Any proof-of-concept code or screenshots
5. Whether you'd like public credit when we publish the fix

We will:

- Acknowledge within **48 hours**.
- Provide an initial assessment within **7 days**.
- Ship a patch as soon as a fix is verified.
- Credit you in `CHANGELOG.md` if you wish.

---

## Threat model — what's in scope

- 🟢 SQL injection · authentication bypass · CSRF · XSS · IDOR — yes, please report.
- 🟢 Secret exposure in repo or logs.
- 🟢 Misuse of the LP solver to DoS the server.
- 🟢 Privilege-escalation in the version-lock workflow.
- 🟢 PDF / CSV injection (e.g. spreadsheet formula injection in exports).

## Out of scope

- 🔴 Social engineering of HMG staff or students.
- 🔴 Physical attacks on Streamlit Cloud / Supabase infrastructure.
- 🔴 Findings that require already-compromised admin credentials.
- 🔴 Volumetric DDoS — that's Streamlit Cloud's responsibility, not ours.

---

## Hardening recommendations for self-hosters

1. **Always set `sslmode = "require"`** in `[supabase]`.
2. **Rotate the Supabase DB password** quarterly.
3. **Enable Connection Pooling** in Supabase to absorb idle-disconnects.
4. **Never commit `.streamlit/secrets.toml`** — `.gitignore` already protects it; verify after every fork.
5. **Lock the production timetable version** (🔒 Version Lock page) before sharing read-only access.
6. **Backup** at least weekly — see `DEPLOYMENT.md › Backups & restore`.

---

*Thank you for helping keep Nigerian school data safe.*
