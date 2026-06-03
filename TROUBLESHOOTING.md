# 🔧 TimetableCraft — Troubleshooting

*Read this if your Streamlit Cloud deploy isn't working.*
*Maintained by HMG Technologies · a subsidiary of HMG Concepts.*

---

## 🍞 Symptom 1: *"Your app is in the oven…"* for 10+ minutes

### Diagnosis

The build is stuck in Streamlit Cloud's **provisioner queue**, before any
Python code runs. The deploy log will show only:

```
🖥 Provisioning machine...
🎛 Preparing system...
⛓ Spinning up manager process...
```

…and then nothing else for ages. It never reaches *"Cloning repository"*,
*"Processing dependencies"*, or *"Uvicorn server started"*.

### Causes (ranked by frequency)

1. **Multiple stuck/abandoned apps on the same Streamlit Cloud account.**
   *This is the #1 cause.* Free-tier accounts have a cap on concurrent
   apps. Every old broken deploy that you never explicitly deleted is
   silently holding a slot.
2. **Streamlit Cloud picked Python 3.14** and is trying to resolve heavy
   compiled dependencies.
3. **Heavy `requirements.txt`** that the provisioner has to pre-stage
   before showing logs.
4. A transient outage on Streamlit Cloud itself
   ([status.streamlit.io](https://status.streamlit.io)).

### Fix — in order

1. **Delete the old apps you're not using.** Go to
   [share.streamlit.io](https://share.streamlit.io). For every app on
   your dashboard that isn't the one you care about:
   *⋮ menu → Delete app.* Keep just **one**.
2. **Make sure `.python-version` exists** at the repo root and contains
   `3.11`. The v5.2.2 release ships this for you.
3. **Make sure `requirements.txt` does NOT contain `psycopg2-binary`**
   unless you actually use the Postgres backend. The v5.2.2 release
   already removed it from the default `requirements.txt`.
4. **Reboot, don't redeploy.** Manage app → **⋮ → Reboot**. Pushing
   another commit while the build is stuck does *not* always unstick
   it; an explicit reboot does.
5. If it's *still* stuck after a full reboot: try changing the **Python
   version** in *Advanced settings* explicitly to **3.11**, then reboot.

---

## 🚨 Symptom 2: Red error card *"Could not start its database"*

This is the **expected behaviour** when something is misconfigured. The
card tells you exactly which backend is active and what to fix.

| If the card says... | Do this |
|---|---|
| *Backend: sqlite* + permission error | The filesystem is read-only. Set `TIMETABLECRAFT_DB_PATH=/tmp/timetablecraft.db`. |
| *Backend: postgres* + connection error | Check the `[postgres]` (or legacy `[supabase]`) block in *Streamlit Cloud → App Settings → Secrets*. Un-pause the project if it's on Supabase free tier. |
| *Backend: postgres* + `psycopg2` not installed | Append `psycopg2-binary>=2.9.9,<3.0` to `requirements.txt`. |

---

## 📦 Symptom 3: `apt-get` errors like *"Unable to locate package #"*

The log shows things like:

```
E: Unable to locate package #
E: Unable to locate package Apt
E: Unable to locate package packages
E: Unable to locate package for
…
```

You have a `packages.txt` on the repo that contains comment lines.
**Streamlit Cloud's `packages.txt` parser does not support comments** —
every whitespace-separated token (including `#`, English words, etc.)
is treated as an apt package name.

**Fix (v5.2.3+):** the official build ships an empty `packages.txt` that
overwrites the broken file. Just upload the new build and the next
deploy will succeed.

**Fix (manual):** open
`https://github.com/<your-account>/timetablecraft/blob/main/packages.txt`
on GitHub → click the 🗑️ trash-can icon → commit.

### ⚠️ The "GitHub Upload Files doesn't delete" trap

> **`Add file → Upload files` on GitHub ONLY adds or overwrites — it
> NEVER deletes.** If a previous release shipped a file and the new
> release simply omits it, the old file lives on forever in the repo
> until you delete it explicitly.

This is why v5.2.1 and v5.2.2 didn't fix the apt error for users who
uploaded via the GitHub web UI — `packages.txt` had been *removed* from
the zip, but the broken copy was still sitting on GitHub. v5.2.3 ships
an empty `packages.txt` specifically so the file gets *overwritten*
(not just untouched) on every upload.

Cheat sheet:

| You want to… | GitHub web UI | git CLI |
|---|---|---|
| Add or update a file | *Add file → Upload files* | `git add file && git push` |
| **Delete a file** | Open file → 🗑️ trash icon → commit | `git rm file && git push` |
| **Delete a folder** | Delete every file inside it (folders disappear when empty) | `git rm -r folder && git push` |

---

## 🖼️ Symptom 4: Blank page — only Streamlit's "status embed" iframe

This was the original outage symptom and is fixed since v5.1: the new
bootstrap calls `st.set_page_config()` *before* anything that could
fail, so even a doomed cold-start renders a real error card.

If you're seeing this in v5.2+, you're probably on an old build. Force
a redeploy from `main`.

---

## ⏱️ Symptom 5: First-boot LP solve times out

```
[scheduler] Phase 2 → LP resolution (34 items)
…hangs…
```

Streamlit Cloud free tier has a ~30 s request budget. On a cold start,
the LP solve can flirt with that limit. v5.1+ catches this gracefully:
the seed survives, only the *initial* timetable isn't auto-generated.
Open the **🚀 Generate Timetable** page and click Generate — second
runs are warm and finish in 2-3 s.

---

## 🔌 Symptom 6: Supabase / Postgres `SSL connection has been closed unexpectedly`

Supabase free-tier idle-disconnects after ~5 minutes of inactivity.
v5.1+ auto-reconnects with a `threading.RLock` + clean
close/reconnect. If you still see this regularly:

1. Enable **Connection Pooling** (Transaction mode) in your Supabase
   project settings.
2. Or upgrade to a paid Supabase tier (no idle disconnects).
3. Or switch to the zero-config SQLite backend by **deleting the
   `[postgres]`/`[supabase]` secrets block** — TimetableCraft will
   fall back automatically.

---

## 🧪 Symptom 7: Smoke test fails locally

```bash
python _smoketest.py
```

If any of the 20 pages fails with an exception:

1. Run `pip install -r requirements.txt` again — the test needs every
   listed dep installed.
2. Make sure your local Python is **3.10+** (Streamlit 1.32+ requires it).
3. Delete the local `timetablecraft.db` to start from a clean DB.
4. If it still fails, open a GitHub issue with the full traceback.

---

*Last updated for **TimetableCraft v5.2.2.** If you hit a symptom not
covered here, please open an issue at the repo or message Adewale at
[+234 810 086 6322](https://wa.me/2348100866322).*
