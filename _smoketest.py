"""
================================================================================
TimetableCraft — _smoketest.py
HMG Technologies · a subsidiary of HMG Concepts
================================================================================
End-to-end smoke test: uses streamlit.testing.v1.AppTest to drive every one
of the 20 pages and assert that none of them raises an exception.

Run it locally:

    python _smoketest.py

Or wire it into CI (returns exit code 1 if any page errors).

It needs the same DB credentials as the main app — either
.streamlit/secrets.toml or the PGHOST / PGDATABASE / PGUSER / PGPASSWORD
environment variables.
================================================================================
"""

import sys
import traceback
from streamlit.testing.v1 import AppTest

PAGES = [
    "🏠 Dashboard",
    "👩‍🏫 Teachers",
    "📚 Subjects",
    "🏫 Classes",
    "🗂️ Class Subjects",
    "👨‍🎓 Students",
    "⚙️ Settings",
    "🎨 Branding",
    "📋 Versions",
    "🔒 Version Lock",
    "🚀 Generate Timetable",
    "📅 View Timetable",
    "🔍 Clash Detector",
    "🔄 Substitutions",
    "📢 Notices",
    "📝 Exam Timetable",
    "📅 Term Calendar",
    "📊 Statistics",
    "📋 Change Log",
    "📤 Export",
]


def err_text(at):
    out = []
    try:
        for e in at.exception:
            out.append(str(e.value))
    except Exception as exc:
        out.append(f"<could not read at.exception: {exc!r}>")
    return out


def run_page(page_label: str):
    at = AppTest.from_file("app.py", default_timeout=120)
    at.run()
    errs = err_text(at)
    if errs:
        return [f"INIT: {e}" for e in errs]
    target = None
    for r in at.sidebar.radio:
        if r.label == "Navigate":
            target = r
            break
    if target is None:
        return ["no 'Navigate' radio found in sidebar"]
    try:
        target.set_value(page_label).run()
    except Exception as exc:
        return [f"set_value raised: {exc!r}"]
    return err_text(at)


def main() -> int:
    bad = {}
    for p in PAGES:
        print(f"== {p} ==", flush=True)
        try:
            errs = run_page(p)
        except Exception as exc:
            errs = [f"Harness exception: {exc!r}\n{traceback.format_exc()}"]
        if errs:
            bad[p] = errs
            for e in errs:
                print("  ❌", str(e).splitlines()[0][:300])
        else:
            print("  ✅ ok")

    print("\n================ SUMMARY ================")
    if not bad:
        print(f"All {len(PAGES)} pages rendered with NO exceptions ✅")
        return 0
    for page, errs in bad.items():
        print(f"\n--- {page} ---")
        for e in errs:
            print(e)
    return 1


if __name__ == "__main__":
    sys.exit(main())
