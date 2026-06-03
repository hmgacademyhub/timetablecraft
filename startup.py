"""
================================================================================
TimetableCraft — startup.py  (v3 — Production / Supabase)
Cold-Start Seeder
HMG Concepts | AI-Augmented Solutions
================================================================================
Called once at app boot from app.py.
  - Runs init_db() every time (idempotent — safe on warm starts)
  - Seeds demo school data only when teachers table is empty
  - Generates a real timetable into v1 on first boot
================================================================================
"""

from db import migrate_v5
from db import (
    init_db, get_all_teachers, set_config,
    add_teacher, update_teacher,
    add_subject, update_subject, get_all_subjects,
    add_class, get_all_classes,
    assign_subjects_to_class, bulk_assign_subjects_by_level,
    add_version, set_active_version,
    get_subject_ids_for_class,
)


def needs_seeding() -> bool:
    # Only return True when we *know* the table is empty.
    # Previous version returned True on *any* exception, which made a
    # transient DB outage trigger a doomed seeder run that killed the
    # whole app's bootstrap and left a blank "status embed" page.
    try:
        return len(get_all_teachers()) == 0
    except Exception:
        return False


def seed_on_cold_start():
    """
    Idempotent boot routine. Only seeds when DB is completely empty.

    All work is wrapped in defensive try/except so a transient DB problem
    (Supabase free-tier pause, idle disconnect, bad secret) bubbles up as
    a normal Streamlit error card instead of crashing the whole script
    before st.set_page_config() can render anything.
    """
    init_db()
    migrate_v5()

    if not needs_seeding():
        return

    print("[startup] 🌱 Empty database — seeding HMG Academy Demo school…")

    # ── School config ──────────────────────────────────────────────────────────
    set_config("school_name",            "HMG Academy Demo")
    set_config("current_term",           "First Term")
    set_config("current_session",        "2024/2025")
    set_config("mon_thu_duration",       "40")
    set_config("fri_duration",           "30")
    set_config("periods_per_day",        "8")
    set_config("day_start_time",         "07:45")
    set_config("assembly_duration",      "15")
    set_config("break_after_slot",       "4")
    set_config("break_duration",         "20")
    set_config("double_periods_enabled", "true")
    set_config("school_days",            "Monday,Tuesday,Wednesday,Thursday,Friday")

    # ── Subjects ───────────────────────────────────────────────────────────────
    jss_defs = [
        ("Mathematics",             5, "#1A56DB", True),
        ("English Language",        5, "#E74C3C", False),
        ("Basic Science",           4, "#27AE60", False),
        ("Basic Technology",        3, "#8E44AD", False),
        ("Social Studies",          3, "#16A085", False),
        ("Civic Education",         2, "#F39C12", False),
        ("Cultural & Creative Art", 2, "#E67E22", False),
        ("Computer Studies",        2, "#2980B9", False),
        ("Physical & Health Edu.",  2, "#1ABC9C", False),
        ("Religious Studies",       2, "#C0392B", False),
    ]
    sss_defs = [
        ("Further Mathematics",     4, "#1A56DB", True),
        ("Physics",                 4, "#8E44AD", False),
        ("Chemistry",               4, "#27AE60", False),
        ("Biology",                 3, "#16A085", False),
        ("Economics",               3, "#F39C12", False),
    ]

    subj_ids = {}
    for name, ppw, color, dbl in jss_defs + sss_defs:
        if name not in subj_ids:
            sid = add_subject(name, ppw, None, color, dbl)
            subj_ids[name] = sid

    # ── Teachers ───────────────────────────────────────────────────────────────
    DAYS = "Monday,Tuesday,Wednesday,Thursday,Friday"
    MWF  = "Monday,Wednesday,Friday"
    TTF  = "Tuesday,Thursday,Friday"

    teachers_def = [
        ("Mr. Adeyemi Tunde",    "fulltime", DAYS, 30, ["Mathematics", "Further Mathematics"]),
        ("Mrs. Okafor Ngozi",    "fulltime", DAYS, 30, ["English Language"]),
        ("Mr. Balogun Segun",    "parttime", MWF,  18, ["Basic Science", "Physics"]),
        ("Miss Eze Adaora",      "fulltime", DAYS, 30, ["Chemistry", "Basic Technology"]),
        ("Mr. Lawal Musa",       "fulltime", DAYS, 28, ["Biology", "Physical & Health Edu."]),
        ("Mrs. Fashola Bimpe",   "fulltime", DAYS, 28, ["Social Studies", "Economics"]),
        ("Mr. Nwosu Emeka",      "parttime", TTF,  15, ["Civic Education", "Cultural & Creative Art"]),
        ("Miss Abiodun Yetunde", "fulltime", DAYS, 25, ["Computer Studies"]),
        ("Mr. Ogundele Femi",    "parttime", MWF,  12, ["Religious Studies"]),
        ("Mrs. Chukwu Amara",    "fulltime", DAYS, 30, ["Mathematics"]),
    ]

    teacher_ids = {}
    for name, stype, avail, maxp, _ in teachers_def:
        tid = add_teacher(name, [], stype, avail, maxp)
        teacher_ids[name] = tid

    # Assign first-eligible teacher to each subject
    assigned = {}
    for name, _, _, _, snames in teachers_def:
        for sname in snames:
            if sname in subj_ids and sname not in assigned:
                assigned[sname] = teacher_ids[name]

    for s in get_all_subjects():
        if s["name"] in assigned:
            update_subject(
                s["id"], s["name"], s["periods_per_week"],
                assigned[s["name"]], s["color_hex"], bool(s["allow_double"])
            )

    # Update teacher.subjects JSON list
    subj_name_to_id = {s["name"]: s["id"] for s in get_all_subjects()}
    for name, stype, avail, maxp, snames in teachers_def:
        tid   = teacher_ids[name]
        s_ids = [subj_name_to_id[n] for n in snames if n in subj_name_to_id]
        update_teacher(tid, name, s_ids, stype, avail, maxp)

    # ── Classes ────────────────────────────────────────────────────────────────
    for lvl in ["JSS 1", "JSS 2", "JSS 3"]:
        for arm in ["A", "B"]:
            add_class(lvl, arm, "JSS")
    for lvl in ["SSS 1", "SSS 2", "SSS 3"]:
        for arm in ["A", "B"]:
            add_class(lvl, arm, "SSS")

    # ── Class–subject mappings ─────────────────────────────────────────────────
    jss_ids = [subj_ids[n] for n, *_ in jss_defs if n in subj_ids]
    sss_ids = [subj_ids["English Language"]] + \
              [subj_ids[n] for n, *_ in sss_defs if n in subj_ids]

    bulk_assign_subjects_by_level("JSS", jss_ids)
    bulk_assign_subjects_by_level("SSS", sss_ids)

    # ── Versions ───────────────────────────────────────────────────────────────
    add_version("v1",         "Version 1 — First Term",  "First Term",  "2024/2025",
                "Auto-seeded on first boot")
    add_version("Term2-Plan", "Second Term Draft",        "Second Term", "2024/2025", "")
    set_active_version("v1")
    set_config("active_version", "v1")

    # ── Generate timetable into v1 ─────────────────────────────────────────────
    # The LP solve takes 10-30s and can blow the 30s request budget on
    # Streamlit Cloud's free tier during first boot. Failures here MUST NOT
    # mask the (already successful) seed: the user can click "Generate" later.
    try:
        from scheduler import generate_timetable
        result = generate_timetable(seed=2024, version="v1")
        print(f"[startup] ✅ Seeded: {result['periods_assigned']} periods | "
              f"{result['stats']['total_conflicts']} conflicts | version=v1")
    except Exception as exc:
        print(f"[startup] ⚠️  Demo seeded but timetable not auto-generated: {exc!r}")
        print("[startup]    → open the 🚀 Generate Timetable page to build it.")
