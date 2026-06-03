"""
================================================================================
TimetableCraft — app.py  (v5.1 — Full Production · HMG-Branded)
HMG Technologies · a subsidiary of HMG Concepts
Built by Adewale Samson Adeagbo — AI-Augmented Solutions Developer
================================================================================
Pages (15 total):
  🏠  Dashboard        🔍  Clash Detector     📊  Statistics
  👩‍🏫  Teachers         🔄  Substitutions      📋  Change Log
  📚  Subjects         📢  Notices            📤  Export
  🏫  Classes          👨‍🎓  Students
  🗂️   Class Subjects   📝  Exam Timetable
  ⚙️   Settings         📅  Term Calendar
  📋  Versions         🔒  Version Lock
  🚀  Generate         🎨  Branding
  📅  View Timetable
================================================================================
"""

import io
import json
import base64
from datetime import date, datetime
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from db import (
    init_db,
    get_all_teachers, get_all_subjects, get_all_classes,
    add_teacher, update_teacher, delete_teacher,
    add_subject, update_subject, delete_subject,
    add_class, update_class, delete_class,
    assign_subjects_to_class, get_subjects_for_class,
    get_subject_ids_for_class, bulk_assign_subjects_by_level,
    get_all_special_slots, add_special_slot,
    update_special_slot, delete_special_slot,
    get_all_versions, add_version, delete_version,
    get_active_version, set_active_version,
    get_all_periods, get_periods_for_class, get_periods_for_teacher,
    get_dashboard_stats, get_all_config, set_config, get_config,
    log_change, get_change_log, clear_change_log,
    add_substitution, get_substitutions, update_substitution_status,
    delete_substitution, get_available_substitutes,
    add_notice, get_notices, delete_notice,
    detect_clashes, swap_periods,
    get_subject_distribution, get_teacher_availability_matrix,
    # v5
    migrate_v5,
    add_student, get_students_for_class, get_all_students,
    update_student, delete_student, bulk_add_students, get_class_size_stats,
    add_exam_slot, get_exam_slots, delete_exam_slot, get_exam_clash_report,
    add_calendar_event, get_calendar_events, delete_calendar_event, get_holiday_dates,
    lock_version, unlock_version, is_version_locked, get_all_locks,
    set_branding, get_branding, get_all_branding,
)
from scheduler import (
    generate_timetable, build_report_data,
    get_teacher_workload_df, get_utilisation_heatmap_df, get_free_period_df
)
from pdf_gen import (
    export_class_timetable_pdf, export_teacher_timetable_pdf,
    export_generation_report, export_master_csv,
    export_statistics_report, export_compact_timetable_pdf,
    export_exam_timetable_pdf, export_student_register_pdf,
    export_teacher_report_pdf,
)
from startup import seed_on_cold_start
import branding as B

# ── Page config MUST come before anything that could fail, so that even a
#    crashed cold-start renders a real Streamlit error card instead of the
#    blank "status embed" iframe the deployed site used to show. ──────────────
st.set_page_config(
    page_title=f"{B.PRODUCT_NAME} — by {B.VENDOR}",
    page_icon=B.PRODUCT_EMOJI,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": (
            f"### {B.PRODUCT_NAME} {B.PRODUCT_VERSION}\n"
            f"{B.PRODUCT_TAGLINE}\n\n"
            f"Built by **{B.VENDOR}** — a subsidiary of **{B.PARENT_BRAND}** "
            f"({B.PARENT_FULL_NAME}), est. {B.FOUNDED_YEAR}, {B.LOCATION}.\n\n"
            f"Designed & engineered by **{B.FOUNDER_NAME}** — "
            f"{B.FOUNDER_TITLE}.\n\n"
            f"- 🌐 [HMG Concepts]({B.URL_CONCEPTS})\n"
            f"- 🎓 [HMG Academy]({B.URL_ACADEMY})\n"
            f"- 👤 [Founder]({B.URL_FOUNDER})\n"
            f"- 💻 [GitHub]({B.URL_GITHUB})\n\n"
            f"*\"{B.PARENT_TAGLINE}\"*"
        ),
        "Get help":  B.URL_WHATSAPP,
        "Report a bug": f"{B.URL_GITHUB}/timetablecraft/issues",
    },
)

# ── Bootstrap (defensive) ─────────────────────────────────────────────────────
try:
    seed_on_cold_start()
except Exception as _boot_exc:
    from db import get_backend
    _backend = get_backend()
    if _backend == "sqlite":
        _help = (
            "**This is unusual** — TimetableCraft's default SQLite backend "
            "needs zero configuration. The most likely causes are:\n\n"
            "1. The hosting environment's filesystem is **read-only** "
            "(some platforms restrict file writes — set the env var "
            "`TIMETABLECRAFT_DB_PATH=/tmp/timetablecraft.db` to use a "
            "writable location).\n"
            "2. The `timetablecraft.db` file exists but is **corrupted** — "
            "delete it and reload to recreate.\n"
            "3. You explicitly set `TIMETABLECRAFT_DB=postgres` but no "
            "Postgres credentials were found.\n\n"
            "See `DEPLOYMENT.md` for the full guide."
        )
    else:
        _help = (
            "**Postgres backend selected but the connection failed.** "
            "Check that:\n\n"
            "1. The `[postgres]` (or legacy `[supabase]`) block in "
            "*Streamlit Cloud → App settings → Secrets* has the right "
            "host / dbname / user / password.\n"
            "2. The DB is **not paused** (Supabase free-tier projects "
            "pause after 7 days of inactivity).\n"
            "3. Your network / firewall allows outbound connections "
            "to the DB host on port 5432.\n\n"
            "Or, to fall back to the zero-config SQLite backend, "
            "**delete the `[postgres]` secrets block** and reload."
        )

    st.error(
        f"🚨 **{B.PRODUCT_NAME} could not start its database.**\n\n"
        f"Active backend: **{_backend}**\n\n"
        f"`{type(_boot_exc).__name__}: {_boot_exc}`\n\n"
        f"{_help}\n\n"
        f"---\n*{B.footer_credit_text()}*"
    )
    st.stop()

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"]{font-family:'Plus Jakarta Sans',sans-serif;}

[data-testid="stSidebar"]{
    background:linear-gradient(160deg,#0F1923 0%,#1E2B3C 100%);
    border-right:1px solid #2A3F5C;
}
[data-testid="stSidebar"] .stRadio label{
    color:#B8C7DD!important;font-size:12px;padding:3px 0;}
[data-testid="stSidebar"] .stRadio label:hover{color:#fff!important;}

.metric-card{background:linear-gradient(135deg,#1A56DB10,#F0F4FF);
  border:1px solid #DCE8FF;border-radius:12px;padding:14px;
  text-align:center;margin-bottom:8px;}
.metric-number{font-size:28px;font-weight:800;color:#1A56DB;line-height:1;}
.metric-label{font-size:10px;color:#6B7FA3;font-weight:600;
  letter-spacing:.5px;text-transform:uppercase;margin-top:4px;}

.page-title{font-size:24px;font-weight:800;color:#0F1923;margin-bottom:2px;}
.page-subtitle{font-size:13px;color:#6B7FA3;margin-bottom:16px;}

.version-pill{display:inline-block;background:#1A56DB;color:white;
  border-radius:20px;padding:3px 12px;font-size:11px;font-weight:700;}
.term-pill{display:inline-block;background:#F5A623;color:white;
  border-radius:20px;padding:3px 12px;font-size:11px;font-weight:700;margin-left:6px;}
.lock-pill{display:inline-block;background:#E53E3E;color:white;
  border-radius:20px;padding:3px 12px;font-size:11px;font-weight:700;margin-left:6px;}

.conflict-item{background:#FFF3F3;border-left:4px solid #E53E3E;
  border-radius:6px;padding:10px 14px;margin-bottom:6px;font-size:12px;}
.clash-high{background:#FFF3F3;border-left:4px solid #E53E3E;
  border-radius:6px;padding:10px 14px;margin-bottom:6px;font-size:12px;}
.clash-medium{background:#FFFBEB;border-left:4px solid #F5A623;
  border-radius:6px;padding:10px 14px;margin-bottom:6px;font-size:12px;}

.success-banner{background:linear-gradient(90deg,#38A169,#48BB78);
  color:white;border-radius:10px;padding:14px 18px;font-weight:700;
  font-size:14px;text-align:center;margin-bottom:14px;}
.warn-banner{background:linear-gradient(90deg,#D69E2E,#ECC94B);
  color:white;border-radius:10px;padding:14px 18px;font-weight:700;
  font-size:14px;text-align:center;margin-bottom:14px;}
.locked-banner{background:linear-gradient(90deg,#E53E3E,#FC8181);
  color:white;border-radius:10px;padding:12px 18px;font-weight:700;
  font-size:13px;text-align:center;margin-bottom:14px;}

.notice-urgent{background:#FFF5F5;border-left:5px solid #E53E3E;
  border-radius:8px;padding:12px 16px;margin-bottom:10px;}
.notice-high{background:#FFF8E6;border-left:5px solid #F5A623;
  border-radius:8px;padding:12px 16px;margin-bottom:10px;}
.notice-normal{background:#F0F9FF;border-left:5px solid #1A56DB;
  border-radius:8px;padding:12px 16px;margin-bottom:10px;}
.notice-low{background:#F7F9FC;border-left:5px solid #A0AEC0;
  border-radius:8px;padding:12px 16px;margin-bottom:10px;}

.cal-holiday{background:#FFF5F5;border-left:4px solid #E53E3E;
  border-radius:6px;padding:6px 12px;margin-bottom:5px;font-size:12px;}
.cal-event{background:#F0F9FF;border-left:4px solid #1A56DB;
  border-radius:6px;padding:6px 12px;margin-bottom:5px;font-size:12px;}
.cal-exam{background:#FFF8E6;border-left:4px solid #F5A623;
  border-radius:6px;padding:6px 12px;margin-bottom:5px;font-size:12px;}
.cal-closure{background:#F7F7F7;border-left:4px solid #718096;
  border-radius:6px;padding:6px 12px;margin-bottom:5px;font-size:12px;}

.avail-free{background:#C6F6D5;color:#276749;border-radius:4px;
  padding:2px 5px;font-size:9px;font-weight:700;margin:1px;display:inline-block;}
.avail-busy{background:#FED7D7;color:#9B2C2C;border-radius:4px;
  padding:2px 5px;font-size:9px;font-weight:700;margin:1px;display:inline-block;}
.avail-off{background:#E2E8F0;color:#718096;border-radius:4px;
  padding:2px 5px;font-size:9px;font-weight:600;margin:1px;display:inline-block;}

.log-row{padding:5px 10px;border-bottom:1px solid #EEF2F8;font-size:12px;}
.log-row:hover{background:#F7F9FC;}

.stButton>button{font-family:'Plus Jakarta Sans',sans-serif;
  font-weight:600;border-radius:8px;}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    # Logo display
    logo_b64 = get_branding("logo_base64", "")
    if logo_b64:
        st.markdown(
            f'<div style="text-align:center;padding:10px 0 6px;">'
            f'<img src="data:image/png;base64,{logo_b64}" '
            f'style="max-height:60px;max-width:140px;object-fit:contain;"/></div>',
            unsafe_allow_html=True)
    else:
        st.markdown(B.sidebar_header_html(), unsafe_allow_html=True)

    page = st.radio("Navigate", [
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
    ], label_visibility="collapsed")

    active_ver = get_active_version()
    locked     = is_version_locked(active_ver)
    term       = get_config("current_term", "First Term")
    session    = get_config("current_session", "2024/2025")
    lock_tag   = f'<span class="lock-pill">🔒 LOCKED</span>' if locked else ""

    # Backend badge — tells the admin at a glance whether they're on
    # the zero-config SQLite default or a managed Postgres cluster.
    from db import get_backend, backend_summary
    backend = get_backend()
    badge_bg, badge_fg, badge_label = (
        ("#1A3A5C", "#7CC1FF", "📦 SQLite")
        if backend == "sqlite"
        else ("#0D3D2A", "#4ADE80", "🐘 Postgres")
    )

    st.markdown(f"""
    <div style="margin-top:16px;padding:9px 12px;background:#0D1720;border-radius:8px;">
      <div style="color:#6B8FAF;font-size:9px;text-transform:uppercase;
                  letter-spacing:.5px;margin-bottom:5px;">Active Timetable</div>
      <span class="version-pill">{active_ver}</span>
      <span class="term-pill">{term}</span>
      {lock_tag}
      <div style="color:#6B8FAF;font-size:9px;margin-top:4px;">{session}</div>
    </div>
    <div style="margin-top:8px;padding:7px 10px;background:{badge_bg};
                border-radius:8px;display:flex;align-items:center;
                justify-content:space-between;" title="{backend_summary()}">
      <span style="color:{badge_fg};font-size:10px;font-weight:700;
                   letter-spacing:.3px;">{badge_label}</span>
      <span style="color:#6B8FAF;font-size:9px;">backend</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown(B.sidebar_footer_html(), unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# 🏠  DASHBOARD
# ════════════════════════════════════════════════════════════════════════════
if page == "🏠 Dashboard":
    school_name = get_config("school_name", "HMG Academy")
    active_ver  = get_active_version()
    locked      = is_version_locked(active_ver)

    st.markdown(f'<div class="page-title">🏠 {school_name}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="page-subtitle">Operations Dashboard · '
        f'<span class="version-pill">{active_ver}</span> '
        f'<span class="term-pill">{get_config("current_term","First Term")}</span>'
        f'{"  <span class=lock-pill>🔒 LOCKED</span>" if locked else ""}'
        f' · {get_config("current_session","2024/2025")}</div>',
        unsafe_allow_html=True)

    # Urgent notices
    for n in [x for x in get_notices() if x["priority"]=="urgent"]:
        st.error(f"📢 **{n['title']}** — {n['body']}")

    stats = get_dashboard_stats(active_ver)

    # Count students
    all_students = get_all_students()
    student_count = len(all_students)

    cols = st.columns(7)
    items = [
        ("Teachers",  stats["teachers"]),
        ("Subjects",  stats["subjects"]),
        ("Classes",   stats["classes"]),
        ("Students",  student_count),
        ("Periods",   stats["periods_assigned"]),
        ("Versions",  stats["versions"]),
        ("Fill Rate",
         f"{stats['periods_assigned']/max(stats['periods_total'],1)*100:.0f}%"
         if stats["periods_total"] else "—"),
    ]
    for col, (label, val) in zip(cols, items):
        col.markdown(f"""
        <div class="metric-card">
          <div class="metric-number">{val}</div>
          <div class="metric-label">{label}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📊 Teacher Workload")
        df = get_teacher_workload_df(active_ver)
        if not df.empty:
            fig = px.bar(df, x="teacher", y="periods",
                         color="periods", color_continuous_scale="Blues")
            fig.update_layout(height=260, margin=dict(l=0,r=0,t=10,b=0),
                               showlegend=False, coloraxis_showscale=False,
                               font=dict(family="Plus Jakarta Sans"),
                               plot_bgcolor="white", paper_bgcolor="white")
            fig.update_xaxes(tickangle=-30, tickfont=dict(size=9))
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Generate a timetable first.")

    with c2:
        st.subheader("🗓️ Period Utilisation Heatmap")
        hm = get_utilisation_heatmap_df(active_ver)
        if not hm.empty:
            fig = go.Figure(go.Heatmap(
                z=hm.values, x=hm.columns.tolist(),
                y=[f"Slot {i}" for i in hm.index],
                colorscale="Blues", zmin=0, zmax=1,
                text=[[f"{v:.0%}" for v in row] for row in hm.values],
                texttemplate="%{text}", showscale=True))
            fig.update_layout(height=260, margin=dict(l=0,r=0,t=10,b=0),
                               font=dict(family="Plus Jakarta Sans"))
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Generate a timetable first.")

    # Class sizes
    st.subheader("👨‍🎓 Class Sizes")
    size_stats = get_class_size_stats()
    if any(s["student_count"] > 0 for s in size_stats):
        size_df = pd.DataFrame(size_stats)
        size_df["class_label"] = size_df["class_name"] + " " + size_df["arm"]
        fig3 = px.bar(size_df, x="class_label", y="student_count",
                      color="level", color_discrete_map={"JSS":"#1A56DB","SSS":"#E74C3C"},
                      labels={"class_label":"Class","student_count":"Students"})
        fig3.update_layout(height=240, margin=dict(l=0,r=0,t=10,b=0),
                            font=dict(family="Plus Jakarta Sans"),
                            plot_bgcolor="white", paper_bgcolor="white")
        fig3.update_xaxes(tickangle=-30, tickfont=dict(size=9))
        st.plotly_chart(fig3, width="stretch")
    else:
        st.info("Add students via the 👨‍🎓 Students page.")

    # Recent activity
    st.subheader("🕐 Recent Activity")
    logs = get_change_log(limit=6)
    if logs:
        for log in logs:
            ts = str(log["created_at"])[:16]
            st.markdown(
                f'<div class="log-row">🔹 <b>{log["action"]}</b> · {log["entity"]} · '
                f'{log["description"]}'
                f'<span style="color:#A0AEC0;float:right">{ts}</span></div>',
                unsafe_allow_html=True)
    else:
        st.caption("No activity yet.")

    # ── About / brand panel ───────────────────────────────────────────────────
    st.markdown(B.about_card_html(), unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# 👩‍🏫  TEACHERS
# ════════════════════════════════════════════════════════════════════════════
elif page == "👩‍🏫 Teachers":
    st.markdown('<div class="page-title">👩‍🏫 Teachers</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Manage staff, availability & weekly capacity</div>',
                unsafe_allow_html=True)

    subjects  = get_all_subjects()
    subj_opts = {s["id"]: s["name"] for s in subjects}
    days_all  = ["Monday","Tuesday","Wednesday","Thursday","Friday"]

    tab_list, tab_add, tab_avail, tab_import = st.tabs([
        "📋 All Teachers","➕ Add Teacher","📅 Availability Matrix","📥 CSV Import"])

    with tab_add:
        with st.form("add_teacher"):
            name       = st.text_input("Full Name *")
            staff_type = st.selectbox("Staff Type",["fulltime","parttime"])
            avail_days = st.multiselect("Available Days", days_all, default=days_all)
            max_p      = st.number_input("Max Periods/Week",1,50,30)
            s_ids      = st.multiselect("Subjects Taught", list(subj_opts.keys()),
                                        format_func=lambda x: subj_opts[x])
            if st.form_submit_button("✅ Add Teacher", type="primary"):
                if not name.strip():
                    st.error("Name required.")
                else:
                    tid = add_teacher(name.strip(), s_ids, staff_type,
                                      ",".join(avail_days), max_p)
                    log_change("CREATE","teacher",f"Added: {name}",tid)
                    st.success(f"'{name}' added!"); st.rerun()

    with tab_list:
        teachers = get_all_teachers()
        if not teachers:
            st.info("No teachers yet.")
        else:
            active_ver = get_active_version()
            for t in teachers:
                pw = len(get_periods_for_teacher(t["id"], active_ver))
                with st.expander(f"**{t['name']}** — {t['staff_type'].title()} | "
                                 f"{pw} periods this version"):
                    c1, c2 = st.columns([4,1])
                    with c1:
                        with st.form(f"edit_t_{t['id']}"):
                            en = st.text_input("Name", t["name"])
                            et = st.selectbox("Type",["fulltime","parttime"],
                                              index=0 if t["staff_type"]=="fulltime" else 1)
                            ed = st.multiselect("Available Days", days_all,
                                                default=t["available_days"].split(","))
                            em = st.number_input("Max Periods/Week",1,50,
                                                  value=t.get("max_periods_per_week",30))
                            es = st.multiselect("Subjects", list(subj_opts.keys()),
                                                default=[s for s in t["subjects"]
                                                         if s in subj_opts],
                                                format_func=lambda x: subj_opts.get(x,str(x)))
                            if st.form_submit_button("💾 Save"):
                                update_teacher(t["id"],en,es,et,",".join(ed),em)
                                log_change("UPDATE","teacher",f"Updated: {en}",t["id"])
                                st.success("Updated!"); st.rerun()
                    with c2:
                        st.write(""); st.write("")
                        if st.button("📄 Report", key=f"rep_t_{t['id']}"):
                            periods = get_periods_for_teacher(t["id"], active_ver)
                            pdf = export_teacher_report_pdf(t, periods, active_ver)
                            st.download_button(
                                f"⬇️ {t['name'].replace(' ','_')}_report.pdf",
                                pdf, f"{t['name'].replace(' ','_')}_report.pdf",
                                "application/pdf", key=f"dl_rep_{t['id']}")
                        if st.button("🗑️ Delete", key=f"dt_{t['id']}"):
                            log_change("DELETE","teacher",f"Deleted: {t['name']}",t["id"])
                            delete_teacher(t["id"]); st.rerun()

    with tab_avail:
        st.subheader("📅 Teacher Availability Matrix")
        st.caption("🟢 Free  🔴 Teaching  ⬜ Not available (parttime)")
        matrix = get_teacher_availability_matrix()
        ppd    = int(get_config("periods_per_day",8))
        days   = get_config("school_days","Monday,Tuesday,Wednesday,Thursday,Friday").split(",")
        if not matrix:
            st.info("No teachers defined.")
        else:
            for tname, day_slots in matrix.items():
                st.markdown(f"**{tname}**")
                cols = st.columns(len(days))
                for ci, day in enumerate(days):
                    with cols[ci]:
                        st.markdown(
                            f'<div style="font-size:10px;font-weight:700;'
                            f'color:#1E2B3C;margin-bottom:3px;">{day[:3]}</div>',
                            unsafe_allow_html=True)
                        free = day_slots.get(day, None)
                        for s in range(1, ppd+1):
                            if free is None:
                                st.markdown(f'<div class="avail-off">{s}</div>',
                                            unsafe_allow_html=True)
                            elif s in free:
                                st.markdown(f'<div class="avail-free">{s}</div>',
                                            unsafe_allow_html=True)
                            else:
                                st.markdown(f'<div class="avail-busy">{s}</div>',
                                            unsafe_allow_html=True)
                st.markdown("---")

    with tab_import:
        st.subheader("📥 Bulk Import Teachers via CSV")
        st.caption("CSV must have columns: `name, staff_type, available_days, max_periods`")
        st.download_button(
            "⬇️ Download Teacher CSV Template",
            data="name,staff_type,available_days,max_periods\n"
                 "Mrs. Adeyemi,fulltime,\"Monday,Tuesday,Wednesday,Thursday,Friday\",30\n"
                 "Mr. Balogun,parttime,\"Monday,Wednesday,Friday\",18\n",
            file_name="teachers_template.csv",
            mime="text/csv")
        uploaded = st.file_uploader("Upload filled CSV", type=["csv"],
                                     key="teacher_csv")
        if uploaded:
            try:
                df = pd.read_csv(uploaded)
                st.dataframe(df, width="stretch")
                if st.button("✅ Import Teachers", type="primary"):
                    added = 0
                    for _, row in df.iterrows():
                        try:
                            tid = add_teacher(
                                str(row.get("name","")).strip(),
                                [],
                                str(row.get("staff_type","fulltime")),
                                str(row.get("available_days",
                                    "Monday,Tuesday,Wednesday,Thursday,Friday")),
                                int(row.get("max_periods",30))
                            )
                            log_change("IMPORT","teacher",
                                       f"CSV import: {row.get('name','')}",tid)
                            added += 1
                        except Exception as e:
                            st.warning(f"Skipped row: {e}")
                    st.success(f"✅ Imported {added} teacher(s).")
                    st.rerun()
            except Exception as e:
                st.error(f"Could not parse CSV: {e}")


# ════════════════════════════════════════════════════════════════════════════
# 📚  SUBJECTS
# ════════════════════════════════════════════════════════════════════════════
elif page == "📚 Subjects":
    st.markdown('<div class="page-title">📚 Subjects</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Configure subjects, periods/week & teacher assignments</div>',
                unsafe_allow_html=True)

    teachers   = get_all_teachers()
    teach_opts = {t["id"]: t["name"] for t in teachers}
    tab_list, tab_add, tab_import = st.tabs([
        "📋 All Subjects","➕ Add Subject","📥 CSV Import"])

    with tab_add:
        with st.form("add_subj"):
            sn  = st.text_input("Subject Name *")
            sp  = st.number_input("Periods/Week",1,15,4)
            st_ = st.selectbox("Assigned Teacher",
                               [None]+list(teach_opts.keys()),
                               format_func=lambda x: "— Unassigned —"
                               if x is None else teach_opts[x])
            sc  = st.color_picker("Colour","#1A56DB")
            sd  = st.checkbox("Allow Double Periods")
            if st.form_submit_button("✅ Add Subject", type="primary"):
                if not sn.strip():
                    st.error("Name required.")
                else:
                    sid = add_subject(sn.strip(), sp, st_, sc, sd)
                    log_change("CREATE","subject",f"Added: {sn}",sid)
                    st.success(f"'{sn}' added!"); st.rerun()

    with tab_list:
        subjects = get_all_subjects()
        if not subjects:
            st.info("No subjects yet.")
        else:
            cols = st.columns(min(len(subjects),6))
            for i, s in enumerate(subjects):
                with cols[i % 6]:
                    st.markdown(
                        f'<div style="background:{s["color_hex"]};color:white;'
                        f'border-radius:8px;padding:8px;text-align:center;'
                        f'font-size:11px;font-weight:700;margin-bottom:8px;">'
                        f'{s["name"]}<br/><span style="font-weight:400">'
                        f'{s["periods_per_week"]}×/wk</span></div>',
                        unsafe_allow_html=True)
            st.markdown("---")
            for s in subjects:
                warn = "" if s.get("teacher_name") else " ⚠️"
                with st.expander(f"**{s['name']}**{warn} — "
                                 f"{s['periods_per_week']}×/wk | "
                                 f"{s.get('teacher_name') or 'Unassigned'}"):
                    c1, c2 = st.columns([4,1])
                    with c1:
                        with st.form(f"edit_s_{s['id']}"):
                            esn = st.text_input("Name", s["name"])
                            esp = st.number_input("Periods/Week",1,15,s["periods_per_week"])
                            est = st.selectbox("Teacher",
                                               [None]+list(teach_opts.keys()),
                                               index=([None]+list(teach_opts.keys()))
                                               .index(s["assigned_teacher_id"])
                                               if s["assigned_teacher_id"]
                                               in teach_opts else 0,
                                               format_func=lambda x: "— Unassigned —"
                                               if x is None else teach_opts[x])
                            esc = st.color_picker("Colour", s["color_hex"])
                            esd = st.checkbox("Allow Double", bool(s["allow_double"]))
                            if st.form_submit_button("💾 Save"):
                                update_subject(s["id"],esn,esp,est,esc,esd)
                                log_change("UPDATE","subject",f"Updated: {esn}",s["id"])
                                st.success("Updated!"); st.rerun()
                    with c2:
                        st.write(""); st.write("")
                        if st.button("🗑️", key=f"ds_{s['id']}"):
                            log_change("DELETE","subject",f"Deleted: {s['name']}",s["id"])
                            delete_subject(s["id"]); st.rerun()

    with tab_import:
        st.subheader("📥 Bulk Import Subjects via CSV")
        st.caption("CSV must have columns: `name, periods_per_week, color_hex`")
        st.download_button(
            "⬇️ Download Subject CSV Template",
            data="name,periods_per_week,color_hex\n"
                 "Mathematics,5,#1A56DB\nEnglish Language,5,#E74C3C\n"
                 "Basic Science,4,#27AE60\n",
            file_name="subjects_template.csv", mime="text/csv")
        uploaded = st.file_uploader("Upload filled CSV", type=["csv"], key="subj_csv")
        if uploaded:
            try:
                df = pd.read_csv(uploaded)
                st.dataframe(df, width="stretch")
                if st.button("✅ Import Subjects", type="primary"):
                    added = 0
                    for _, row in df.iterrows():
                        try:
                            sid = add_subject(
                                str(row.get("name","")).strip(),
                                int(row.get("periods_per_week",4)),
                                None,
                                str(row.get("color_hex","#4A90D9")),
                                False)
                            log_change("IMPORT","subject",
                                       f"CSV import: {row.get('name','')}",sid)
                            added += 1
                        except Exception as e:
                            st.warning(f"Skipped: {e}")
                    st.success(f"✅ Imported {added} subject(s)."); st.rerun()
            except Exception as e:
                st.error(f"Could not parse CSV: {e}")


# ════════════════════════════════════════════════════════════════════════════
# 🏫  CLASSES
# ════════════════════════════════════════════════════════════════════════════
elif page == "🏫 Classes":
    st.markdown('<div class="page-title">🏫 Classes</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Manage class sections (JSS 1A, SSS 2B, etc.)</div>',
                unsafe_allow_html=True)

    tab_list, tab_add, tab_bulk = st.tabs(["📋 All","➕ Add","📦 Bulk Add"])

    with tab_add:
        with st.form("add_cls"):
            cn = st.text_input("Class Name *", placeholder="JSS 1")
            ca = st.text_input("Arm *","A")
            cl = st.selectbox("Level",["JSS","SSS"])
            if st.form_submit_button("✅ Add", type="primary"):
                if cn.strip():
                    cid = add_class(cn.strip(), ca.strip().upper(), cl)
                    log_change("CREATE","class",f"Added: {cn} {ca}",cid)
                    st.success("Added!"); st.rerun()
                else:
                    st.error("Name required.")

    with tab_bulk:
        st.subheader("Quick Populate — Nigerian Curriculum")
        c1, c2 = st.columns(2)
        with c1:
            jss_arms = st.text_input("JSS Arms","A,B,C")
            if st.button("➕ Add JSS 1–3"):
                for lvl in ["JSS 1","JSS 2","JSS 3"]:
                    for arm in [a.strip().upper()
                                for a in jss_arms.split(",") if a.strip()]:
                        try:
                            cid = add_class(lvl, arm, "JSS")
                            log_change("CREATE","class",f"Bulk: {lvl} {arm}",cid)
                        except: pass
                st.success("JSS classes added!"); st.rerun()
        with c2:
            sss_arms = st.text_input("SSS Arms","A,B")
            if st.button("➕ Add SSS 1–3"):
                for lvl in ["SSS 1","SSS 2","SSS 3"]:
                    for arm in [a.strip().upper()
                                for a in sss_arms.split(",") if a.strip()]:
                        try:
                            cid = add_class(lvl, arm, "SSS")
                            log_change("CREATE","class",f"Bulk: {lvl} {arm}",cid)
                        except: pass
                st.success("SSS classes added!"); st.rerun()

    with tab_list:
        classes = get_all_classes()
        if not classes:
            st.info("No classes yet.")
        else:
            df = pd.DataFrame(classes)[["name","arm","level"]]
            df.columns = ["Class","Arm","Level"]
            st.dataframe(df, width="stretch", hide_index=True)
            st.caption(f"Total: {len(classes)} sections")
            st.markdown("---")
            for c in classes:
                with st.expander(f"{c['name']} {c['arm']} ({c['level']})"):
                    cc1, cc2 = st.columns([4,1])
                    with cc1:
                        with st.form(f"edit_c_{c['id']}"):
                            ecn = st.text_input("Name", c["name"])
                            eca = st.text_input("Arm", c["arm"])
                            ecl = st.selectbox("Level",["JSS","SSS"],
                                               index=0 if c["level"]=="JSS" else 1)
                            if st.form_submit_button("💾 Save"):
                                update_class(c["id"],ecn,eca,ecl)
                                log_change("UPDATE","class",
                                           f"Updated: {ecn} {eca}",c["id"])
                                st.success("Updated!"); st.rerun()
                    with cc2:
                        st.write(""); st.write("")
                        if st.button("🗑️", key=f"dc_{c['id']}"):
                            log_change("DELETE","class",
                                       f"Deleted: {c['name']} {c['arm']}",c["id"])
                            delete_class(c["id"]); st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# 🗂️  CLASS SUBJECTS
# ════════════════════════════════════════════════════════════════════════════
elif page == "🗂️ Class Subjects":
    st.markdown('<div class="page-title">🗂️ Class Subjects</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Map which subjects each class takes. '
        'No mapping = all subjects scheduled.</div>', unsafe_allow_html=True)

    classes  = get_all_classes()
    subjects = get_all_subjects()
    subj_map = {s["id"]: s for s in subjects}

    if not classes or not subjects:
        st.warning("Add classes and subjects first.")
    else:
        st.subheader("⚡ Bulk Assign by Level")
        bc1, bc2 = st.columns(2)
        with bc1:
            jss_sel = st.multiselect("JSS Subjects",
                                     [s["id"] for s in subjects],
                                     format_func=lambda x: subj_map[x]["name"],
                                     key="bulk_jss")
            if st.button("✅ Apply to All JSS Classes"):
                n = bulk_assign_subjects_by_level("JSS", jss_sel)
                log_change("BULK","class_subjects",
                           f"JSS: {len(jss_sel)} subjects → {n} classes")
                st.success(f"Applied to {n} JSS classes."); st.rerun()
        with bc2:
            sss_sel = st.multiselect("SSS Subjects",
                                     [s["id"] for s in subjects],
                                     format_func=lambda x: subj_map[x]["name"],
                                     key="bulk_sss")
            if st.button("✅ Apply to All SSS Classes"):
                n = bulk_assign_subjects_by_level("SSS", sss_sel)
                log_change("BULK","class_subjects",
                           f"SSS: {len(sss_sel)} subjects → {n} classes")
                st.success(f"Applied to {n} SSS classes."); st.rerun()

        st.markdown("---")
        for cls in classes:
            current_ids = get_subject_ids_for_class(cls["id"])
            label = f"{cls['name']} {cls['arm']} ({cls['level']})"
            tag   = f"✅ {len(current_ids)}" if current_ids else "⚠️ None"
            with st.expander(f"**{label}** — {tag}"):
                new_ids = st.multiselect(
                    "Subjects", [s["id"] for s in subjects],
                    default=current_ids,
                    format_func=lambda x: subj_map[x]["name"],
                    key=f"cs_{cls['id']}")
                sc1, sc2 = st.columns(2)
                with sc1:
                    if st.button("💾 Save", key=f"save_cs_{cls['id']}"):
                        assign_subjects_to_class(cls["id"], new_ids)
                        log_change("UPDATE","class_subjects",
                                   f"{label} → {len(new_ids)}",cls["id"])
                        st.success("Saved!"); st.rerun()
                with sc2:
                    if st.button("🗑️ Clear", key=f"clr_cs_{cls['id']}"):
                        assign_subjects_to_class(cls["id"], [])
                        st.info("Cleared."); st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# 👨‍🎓  STUDENTS
# ════════════════════════════════════════════════════════════════════════════
elif page == "👨‍🎓 Students":
    st.markdown('<div class="page-title">👨‍🎓 Students</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Manage student registers, bulk import, '
        'and download class lists as PDF.</div>', unsafe_allow_html=True)

    classes   = get_all_classes()
    cls_opts  = {c["id"]: f"{c['name']} {c['arm']} ({c['level']})" for c in classes}

    if not classes:
        st.warning("Add classes first.")
    else:
        tab_reg, tab_add, tab_import = st.tabs([
            "📋 Class Register","➕ Add Student","📥 CSV Import"])

        with tab_reg:
            sel_cls = st.selectbox("Select Class", list(cls_opts.keys()),
                                   format_func=lambda x: cls_opts[x], key="reg_cls")
            students = get_students_for_class(sel_cls)
            if not students:
                st.info("No students in this class yet.")
            else:
                df = pd.DataFrame(students)[["roll_number","last_name",
                                              "first_name","gender"]]
                df.columns = ["Roll No.","Last Name","First Name","Gender"]
                st.dataframe(df, width="stretch", hide_index=True)
                st.caption(f"Total: {len(students)} students | "
                           f"Male: {sum(1 for s in students if s['gender']=='M')} | "
                           f"Female: {sum(1 for s in students if s['gender']=='F')}")

                col_pdf, col_csv = st.columns(2)
                with col_pdf:
                    if st.button("📄 Download Register PDF", width="stretch"):
                        pdf = export_student_register_pdf(sel_cls, students)
                        cls_label = cls_opts[sel_cls].replace(" ","_").replace("(","").replace(")","")
                        st.download_button(f"⬇️ {cls_label}_register.pdf",
                                           pdf, f"{cls_label}_register.pdf",
                                           "application/pdf", width="stretch")
                with col_csv:
                    if st.button("📊 Download as CSV", width="stretch"):
                        csv_bytes = df.to_csv(index=False).encode()
                        cls_label = cls_opts[sel_cls].replace(" ","_").replace("(","").replace(")","")
                        st.download_button(f"⬇️ {cls_label}_students.csv",
                                           csv_bytes, f"{cls_label}_students.csv",
                                           "text/csv", width="stretch")

                st.markdown("---")
                st.caption("Individual student management:")
                for s in students:
                    with st.expander(f"{s['roll_number']} — {s['last_name']}, {s['first_name']}"):
                        with st.form(f"edit_stu_{s['id']}"):
                            ef = st.text_input("First Name", s["first_name"])
                            el = st.text_input("Last Name",  s["last_name"])
                            er = st.text_input("Roll No.",   s["roll_number"])
                            eg = st.selectbox("Gender",["M","F"],
                                              index=0 if s["gender"]=="M" else 1)
                            ec_id = st.selectbox("Class", list(cls_opts.keys()),
                                                  index=list(cls_opts.keys()).index(s["class_id"])
                                                  if s["class_id"] in cls_opts else 0,
                                                  format_func=lambda x: cls_opts[x])
                            b1, b2 = st.columns(2)
                            with b1:
                                if st.form_submit_button("💾 Save"):
                                    update_student(s["id"],ef,el,er,ec_id,eg)
                                    st.success("Updated!"); st.rerun()
                            with b2:
                                if st.form_submit_button("🗑️ Delete"):
                                    delete_student(s["id"]); st.rerun()

        with tab_add:
            with st.form("add_student"):
                cls_a = st.selectbox("Class *", list(cls_opts.keys()),
                                     format_func=lambda x: cls_opts[x])
                c1, c2 = st.columns(2)
                with c1:
                    fn = st.text_input("First Name *")
                    rn = st.text_input("Roll Number *",
                                       placeholder="e.g. JSS1A-001")
                with c2:
                    ln = st.text_input("Last Name *")
                    gn = st.selectbox("Gender",["M","F"])
                if st.form_submit_button("✅ Add Student", type="primary"):
                    if not fn.strip() or not ln.strip() or not rn.strip():
                        st.error("First name, last name and roll number required.")
                    else:
                        try:
                            sid = add_student(fn.strip(),ln.strip(),
                                              rn.strip(),cls_a,gn)
                            log_change("CREATE","student",
                                       f"Added: {fn} {ln} ({rn})",sid)
                            st.success("Student added!"); st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

        with tab_import:
            st.subheader("📥 Bulk Import Students via CSV")
            st.caption("CSV must have: `first_name, last_name, roll_number, gender`")
            target_cls = st.selectbox("Import into class",
                                      list(cls_opts.keys()),
                                      format_func=lambda x: cls_opts[x],
                                      key="import_cls")
            st.download_button(
                "⬇️ Download Student CSV Template",
                data="first_name,last_name,roll_number,gender\n"
                     "Chukwuemeka,Okonkwo,JSS1A-001,M\n"
                     "Aisha,Bello,JSS1A-002,F\n",
                file_name="students_template.csv", mime="text/csv")
            uploaded = st.file_uploader("Upload CSV", type=["csv"], key="stu_csv")
            if uploaded:
                try:
                    df = pd.read_csv(uploaded)
                    df.columns = [c.strip().lower() for c in df.columns]
                    st.dataframe(df, width="stretch")
                    if st.button("✅ Import Students", type="primary"):
                        rows = df.to_dict("records")
                        added, skipped = bulk_add_students(rows, target_cls)
                        log_change("IMPORT","student",
                                   f"CSV: {added} added, {skipped} skipped "
                                   f"into class {target_cls}")
                        st.success(f"✅ Added {added}, skipped {skipped}.")
                        st.rerun()
                except Exception as e:
                    st.error(f"CSV error: {e}")


# ════════════════════════════════════════════════════════════════════════════
# ⚙️  SETTINGS
# ════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ Settings":
    st.markdown('<div class="page-title">⚙️ Settings</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Period durations, special slots, term & session</div>',
                unsafe_allow_html=True)

    config = get_all_config()
    tab_gen, tab_special = st.tabs(["🏫 General","🔔 Special Slots"])

    with tab_gen:
        with st.form("settings_form"):
            st.subheader("School Info")
            sname = st.text_input("School Name",
                                   config.get("school_name","HMG Academy"))
            c1, c2 = st.columns(2)
            with c1:
                term = st.selectbox("Current Term",
                                    ["First Term","Second Term","Third Term"],
                                    index=["First Term","Second Term","Third Term"]
                                    .index(config.get("current_term","First Term")))
            with c2:
                sess = st.text_input("Academic Session",
                                      config.get("current_session","2024/2025"))
            st.subheader("Period Durations")
            r1, r2, r3 = st.columns(3)
            with r1: mth = st.number_input("Mon–Thu (min)",20,90,
                              int(config.get("mon_thu_duration",40)))
            with r2: fri = st.number_input("Friday (min)",15,60,
                              int(config.get("fri_duration",30)))
            with r3: ppd = st.number_input("Periods/Day",4,12,
                              int(config.get("periods_per_day",8)))
            st.subheader("Timing")
            t1, t2, t3 = st.columns(3)
            with t1: day_start = st.text_input("Day Start (HH:MM)",
                                                config.get("day_start_time","08:00"))
            with t2: asm_dur   = st.number_input("Assembly (min, 0=off)",0,30,
                                     int(config.get("assembly_duration",15)))
            with t3: dbl_en    = st.checkbox("Enable Double Periods",
                                              config.get("double_periods_enabled","true")=="true")
            all_days = ["Monday","Tuesday","Wednesday","Thursday","Friday",
                        "Saturday","Sunday"]
            cur_days = config.get("school_days",
                        "Monday,Tuesday,Wednesday,Thursday,Friday").split(",")
            sch_days = st.multiselect("Active School Days", all_days, default=cur_days)
            if st.form_submit_button("💾 Save Settings", type="primary"):
                set_config("school_name",            sname)
                set_config("current_term",           term)
                set_config("current_session",        sess)
                set_config("mon_thu_duration",       str(mth))
                set_config("fri_duration",           str(fri))
                set_config("periods_per_day",        str(ppd))
                set_config("day_start_time",         day_start.strip())
                set_config("assembly_duration",      str(asm_dur))
                set_config("double_periods_enabled", "true" if dbl_en else "false")
                set_config("school_days",            ",".join(sch_days))
                log_change("UPDATE","settings","School config updated")
                st.success("✅ Settings saved!"); st.rerun()

    with tab_special:
        st.subheader("🔔 Special Slots")
        st.caption("Position 0 = before Slot 1 (Assembly). N = after Slot N.")
        specials = get_all_special_slots()
        ppd_val  = int(config.get("periods_per_day",8))
        for sp in specials:
            with st.expander(f"**{sp['label']}** — pos {sp['position']}, "
                             f"{sp['duration']} min"):
                with st.form(f"sp_{sp['id']}"):
                    sc1, sc2, sc3 = st.columns(3)
                    with sc1: sp_l = st.text_input("Label", sp["label"])
                    with sc2: sp_p = st.number_input("After Slot #",0,ppd_val,sp["position"])
                    with sc3: sp_d = st.number_input("Duration (min)",5,90,sp["duration"])
                    sp_c  = st.color_picker("Colour", sp["color_hex"])
                    sp_dy = st.multiselect("Apply on Days",
                                ["Monday","Tuesday","Wednesday","Thursday","Friday"],
                                default=sp["days"].split(","))
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.form_submit_button("💾 Save"):
                            update_special_slot(sp["id"],sp_l,sp_p,
                                                sp_d,sp_c,",".join(sp_dy))
                            st.success("Saved!"); st.rerun()
                    with b2:
                        if st.form_submit_button("🗑️ Delete"):
                            delete_special_slot(sp["id"]); st.rerun()
        st.markdown("---")
        st.subheader("➕ Add Special Slot")
        with st.form("add_special"):
            nc1, nc2, nc3 = st.columns(3)
            with nc1: ns_l = st.text_input("Label","Lunch")
            with nc2: ns_p = st.number_input("After Slot #",0,ppd_val,6)
            with nc3: ns_d = st.number_input("Duration (min)",5,90,30)
            ns_c  = st.color_picker("Colour","#E8B4B8")
            ns_dy = st.multiselect("Apply on Days",
                        ["Monday","Tuesday","Wednesday","Thursday","Friday"],
                        default=["Monday","Tuesday","Wednesday","Thursday","Friday"])
            if st.form_submit_button("➕ Add"):
                add_special_slot(ns_l, ns_p, ns_d, ns_c, ",".join(ns_dy))
                st.success(f"'{ns_l}' added!"); st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# 🎨  BRANDING
# ════════════════════════════════════════════════════════════════════════════
elif page == "🎨 Branding":
    st.markdown('<div class="page-title">🎨 School Branding</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Upload your school logo — appears on the sidebar '
        'and on all PDF exports.</div>', unsafe_allow_html=True)

    branding = get_all_branding()

    col1, col2 = st.columns([1,2])
    with col1:
        logo_b64 = branding.get("logo_base64","")
        if logo_b64:
            st.markdown("**Current Logo:**")
            st.markdown(
                f'<img src="data:image/png;base64,{logo_b64}" '
                f'style="max-width:200px;max-height:120px;'
                f'object-fit:contain;border:1px solid #E2E8F4;'
                f'border-radius:8px;padding:8px;"/>',
                unsafe_allow_html=True)
        else:
            st.info("No logo uploaded yet.")

    with col2:
        st.subheader("Upload Logo")
        st.caption("PNG or JPG, recommended size 300×100px, max 500KB")
        logo_file = st.file_uploader("Choose logo file",
                                      type=["png","jpg","jpeg"],
                                      key="logo_upload")
        if logo_file:
            if logo_file.size > 500_000:
                st.error("File too large. Maximum 500KB.")
            else:
                logo_bytes  = logo_file.read()
                logo_b64_new = base64.b64encode(logo_bytes).decode()
                st.image(logo_bytes, caption="Preview", width=200)
                if st.button("✅ Save Logo", type="primary"):
                    set_branding("logo_base64", logo_b64_new)
                    log_change("UPDATE","branding","Logo uploaded")
                    st.success("Logo saved! Refresh the page to see it in the sidebar.")
                    st.rerun()

        if branding.get("logo_base64"):
            if st.button("🗑️ Remove Logo"):
                set_branding("logo_base64","")
                log_change("DELETE","branding","Logo removed")
                st.success("Logo removed."); st.rerun()

    st.markdown("---")
    st.subheader("Additional Branding")
    with st.form("branding_form"):
        motto    = st.text_input("School Motto",
                                  branding.get("motto","Excellence in Education"))
        address  = st.text_area("School Address",
                                 branding.get("address",""), height=80)
        phone    = st.text_input("Phone / Contact",  branding.get("phone",""))
        email    = st.text_input("Email",             branding.get("email",""))
        if st.form_submit_button("💾 Save Branding"):
            set_branding("motto",   motto)
            set_branding("address", address)
            set_branding("phone",   phone)
            set_branding("email",   email)
            log_change("UPDATE","branding","Branding details updated")
            st.success("Branding saved!"); st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# 📋  VERSIONS
# ════════════════════════════════════════════════════════════════════════════
elif page == "📋 Versions":
    st.markdown('<div class="page-title">📋 Timetable Versions</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Named snapshots per term. '
        'Each version holds its own complete period set.</div>',
        unsafe_allow_html=True)

    versions   = get_all_versions()
    active_ver = get_active_version()
    ver_tags   = [v["version_tag"] for v in versions]
    locks      = {l["version_tag"] for l in get_all_locks()}

    st.subheader("🔀 Switch Active Version")
    ver_labels = {v["version_tag"]: f"{v['version_tag']} — {v['label']}"
                  for v in versions}
    cur_idx    = ver_tags.index(active_ver) if active_ver in ver_tags else 0
    sel_ver    = st.selectbox("Active Version", ver_tags, index=cur_idx,
                               format_func=lambda x: ver_labels.get(x,x))
    if st.button("✅ Set as Active", type="primary"):
        set_active_version(sel_ver)
        set_config("active_version", sel_ver)
        log_change("UPDATE","version",f"Active → {sel_ver}")
        st.success(f"Active → {sel_ver}"); st.rerun()

    st.markdown("---")
    for v in versions:
        is_active = v["version_tag"] == active_ver
        is_locked = v["version_tag"] in locks
        tags = ("🟢 ACTIVE" if is_active else "") + (" 🔒 LOCKED" if is_locked else "")
        with st.expander(f"**{v['version_tag']}** {tags} — "
                         f"{v['label']} | {v['term']} · {v['session']}"):
            st.caption(f"Created: {str(v['created_at'])[:16]}")
            if v["notes"]: st.write(v["notes"])
            if not is_active and not is_locked:
                if st.button(f"🗑️ Delete", key=f"dv_{v['version_tag']}"):
                    delete_version(v["version_tag"])
                    log_change("DELETE","version",f"Deleted: {v['version_tag']}")
                    st.warning("Deleted."); st.rerun()
            elif is_locked:
                st.caption("🔒 Locked — go to Version Lock page to unlock.")

    st.markdown("---")
    st.subheader("➕ New Version")
    with st.form("new_ver"):
        vc1, vc2 = st.columns(2)
        with vc1: nv_tag  = st.text_input("Version Tag *", placeholder="v2 or Term2-Draft")
        with vc2: nv_lbl  = st.text_input("Label *", placeholder="Second Term Draft")
        vc3, vc4 = st.columns(2)
        with vc3: nv_term = st.selectbox("Term",
                                          ["First Term","Second Term","Third Term"])
        with vc4: nv_sess = st.text_input("Session",
                                           get_config("current_session","2024/2025"))
        nv_notes = st.text_area("Notes", height=60)
        if st.form_submit_button("✅ Create", type="primary"):
            if not nv_tag.strip() or not nv_lbl.strip():
                st.error("Tag and label required.")
            else:
                add_version(nv_tag.strip(), nv_lbl.strip(),
                            nv_term, nv_sess, nv_notes)
                log_change("CREATE","version",f"Created: {nv_tag}")
                st.success(f"'{nv_tag}' created!"); st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# 🔒  VERSION LOCK
# ════════════════════════════════════════════════════════════════════════════
elif page == "🔒 Version Lock":
    st.markdown('<div class="page-title">🔒 Version Lock</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Lock a timetable version to prevent accidental '
        'regeneration or deletion. Locked versions are read-only.</div>',
        unsafe_allow_html=True)

    versions = get_all_versions()
    locks    = {l["version_tag"]: l for l in get_all_locks()}
    ver_tags = [v["version_tag"] for v in versions]

    for v in versions:
        is_locked = v["version_tag"] in locks
        lock_info = locks.get(v["version_tag"],{})
        status = "🔒 LOCKED" if is_locked else "🔓 Unlocked"
        with st.expander(f"**{v['version_tag']}** {status} — {v['label']}"):
            if is_locked:
                st.markdown(f"**Locked at:** {str(lock_info.get('locked_at',''))[:16]}")
                st.markdown(f"**Reason:** {lock_info.get('reason','—')}")
                if st.button(f"🔓 Unlock {v['version_tag']}",
                             key=f"unlock_{v['version_tag']}"):
                    unlock_version(v["version_tag"])
                    st.success(f"Unlocked: {v['version_tag']}"); st.rerun()
            else:
                with st.form(f"lock_{v['version_tag']}"):
                    reason = st.text_input("Lock reason (optional)",
                                           placeholder="Approved for distribution")
                    if st.form_submit_button("🔒 Lock This Version",
                                             type="primary"):
                        lock_version(v["version_tag"], reason)
                        st.success(f"Locked: {v['version_tag']}"); st.rerun()

    st.markdown("---")
    st.caption("💡 **How locking works:** A locked version's timetable data remains "
               "fully visible and exportable. The lock prevents it from being deleted "
               "or regenerated. Use this after a timetable has been approved and "
               "distributed to staff.")


# ════════════════════════════════════════════════════════════════════════════
# 🚀  GENERATE
# ════════════════════════════════════════════════════════════════════════════
elif page == "🚀 Generate Timetable":
    st.markdown('<div class="page-title">🚀 Generate Timetable</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Constraint satisfaction · greedy initialisation '
        '· LP conflict resolution</div>', unsafe_allow_html=True)

    active_ver = get_active_version()
    versions   = get_all_versions()
    ver_tags   = [v["version_tag"] for v in versions]
    stats      = get_dashboard_stats(active_ver)

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Teachers", stats["teachers"])
    c2.metric("Subjects", stats["subjects"])
    c3.metric("Classes",  stats["classes"])
    c4.metric("Version",  active_ver)

    st.markdown("---")
    subjects   = get_all_subjects()
    unassigned = [s for s in subjects if not s.get("assigned_teacher_id")]
    issues     = []
    if stats["teachers"] == 0: issues.append("❌ No teachers.")
    if stats["subjects"] == 0: issues.append("❌ No subjects.")
    if stats["classes"]  == 0: issues.append("❌ No classes.")
    if unassigned:
        issues.append(f"⚠️ {len(unassigned)} unassigned subject(s): "
                      + ", ".join(s["name"] for s in unassigned))
    if issues:
        st.warning("**Pre-flight:**\n" + "\n".join(f"- {i}" for i in issues))

    gc1, gc2 = st.columns(2)
    with gc1:
        gen_ver = st.selectbox("Generate into version", ver_tags,
                               index=ver_tags.index(active_ver)
                               if active_ver in ver_tags else 0)
    with gc2:
        seed = st.number_input("Random seed",0,9999,42)

    # Lock check
    if is_version_locked(gen_ver):
        st.markdown(
            f'<div class="locked-banner">🔒 Version <b>{gen_ver}</b> is LOCKED. '
            f'Unlock it on the Version Lock page before regenerating.</div>',
            unsafe_allow_html=True)
    else:
        existing = get_all_periods(gen_ver)
        if existing:
            st.warning(f"**{gen_ver}** has {len(existing)} periods — will be replaced.")

        disabled = any("❌" in i for i in issues)
        if st.button("🚀 Generate", type="primary",
                     width="stretch", disabled=disabled):
            with st.spinner("Running engine…"):
                result = generate_timetable(seed=int(seed), version=gen_ver)
            log_change("GENERATE","timetable",
                       f"Generated {result['periods_assigned']} periods → {gen_ver}",
                       changed_by="scheduler")
            if result["success"]:
                st.markdown(
                    f'<div class="success-banner">✅ '
                    f'{result["periods_assigned"]} periods · '
                    f'zero constraint violations · {gen_ver}</div>',
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    f'<div class="warn-banner">⚠️ '
                    f'{result["periods_assigned"]} periods · '
                    f'{result["stats"]["total_conflicts"]} unresolved</div>',
                    unsafe_allow_html=True)

            st.session_state["last_result"]      = result
            st.session_state["last_report_data"] = build_report_data(result)

            if result["stats"].get("teacher_loads"):
                st.subheader("📊 Teacher Load")
                ld = pd.DataFrame(
                    list(result["stats"]["teacher_loads"].items()),
                    columns=["Teacher","Periods/Week"]
                ).sort_values("Periods/Week", ascending=False)
                fig = px.bar(ld, x="Teacher", y="Periods/Week",
                             color="Periods/Week", color_continuous_scale="Blues")
                fig.update_layout(height=230, margin=dict(l=0,r=0,t=10,b=0),
                                   coloraxis_showscale=False, showlegend=False,
                                   font=dict(family="Plus Jakarta Sans"),
                                   plot_bgcolor="white", paper_bgcolor="white")
                fig.update_xaxes(tickangle=-30)
                st.plotly_chart(fig, width="stretch")

            if result["conflicts"]:
                st.subheader("⚠️ Conflict Report")
                for c in result["conflicts"]:
                    st.markdown(
                        f'<div class="conflict-item"><b>'
                        f'{c.get("class","—")} / {c.get("subject","—")}'
                        f'</b><br/>{c.get("reason","—")}</div>',
                        unsafe_allow_html=True)
            else:
                st.success("✅ Zero conflicts.")

    if "last_report_data" in st.session_state:
        st.markdown("---")
        if st.button("📄 Download Generation Report PDF"):
            with st.spinner("Building…"):
                pdf = export_generation_report(st.session_state["last_report_data"])
            st.download_button("⬇️ generation_report.pdf", pdf,
                               "generation_report.pdf","application/pdf",
                               width="stretch")


# ════════════════════════════════════════════════════════════════════════════
# 📅  VIEW TIMETABLE
# ════════════════════════════════════════════════════════════════════════════
elif page == "📅 View Timetable":
    st.markdown('<div class="page-title">📅 View Timetable</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Colour-coded grid + period swap tool</div>',
                unsafe_allow_html=True)

    periods_per_day = int(get_config("periods_per_day",8))
    specials        = get_all_special_slots()
    special_map     = {int(s["position"]): s for s in specials}
    versions        = get_all_versions()
    ver_tags        = [v["version_tag"] for v in versions]
    active_ver      = get_active_version()

    top1, top2 = st.columns([2,1])
    with top1: view_mode = st.radio("View Mode",["By Class","By Teacher"],horizontal=True)
    with top2:
        sel_ver = st.selectbox("Version", ver_tags,
                               index=ver_tags.index(active_ver)
                               if active_ver in ver_tags else 0,
                               key="view_ver")

    def render_grid(present_days, slot_map, mode="class"):
        html = ('<table style="width:100%;border-collapse:collapse;'
                'font-family:Plus Jakarta Sans,sans-serif;font-size:11px;">')
        html += ('<tr><th style="background:#1E2B3C;color:white;'
                 'padding:8px;min-width:55px;">Period</th>')
        for day in present_days:
            html += (f'<th style="background:#1E2B3C;color:white;'
                     f'padding:8px;text-align:center;">{day}</th>')
        html += '</tr>'
        if 0 in special_map:
            sp = special_map[0]; sp_bg = sp["color_hex"]
            html += (f'<tr><td style="background:{sp_bg};color:white;'
                     f'font-weight:700;padding:5px 8px;text-align:center;">'
                     f'{sp["label"]}</td>')
            for day in present_days:
                if day in sp["days"].split(","):
                    html += (f'<td style="background:{sp_bg};color:white;'
                             f'text-align:center;padding:5px;">'
                             f'<b>{sp["label"]}</b> {sp["duration"]}min</td>')
                else:
                    html += '<td style="background:#f5f5f5;"></td>'
            html += '</tr>'
        for slot in range(1, periods_per_day+1):
            row_bg = "#FFF" if slot%2==0 else "#F7F9FC"
            html  += f'<tr style="background:{row_bg};">'
            html  += (f'<td style="font-weight:700;padding:7px 10px;'
                      f'color:#1E2B3C;text-align:center;">{slot}</td>')
            for day in present_days:
                rec = slot_map.get((day,slot))
                if mode=="class":
                    if rec and rec.get("subject_name"):
                        bg  = rec.get("color_hex","#4A90D9")
                        dbl = " 🔁" if rec.get("is_double") else ""
                        html += (f'<td style="padding:4px;">'
                                 f'<div style="background:{bg};color:white;'
                                 f'border-radius:6px;padding:6px 4px;'
                                 f'text-align:center;line-height:1.4;">'
                                 f'<b>{rec["subject_name"]}{dbl}</b><br/>'
                                 f'<span style="font-size:9px;">'
                                 f'{rec.get("teacher_name","")}</span><br/>'
                                 f'<span style="font-size:8px;opacity:.85">'
                                 f'{rec["start_time"]}–{rec["end_time"]}</span>'
                                 f'</div></td>')
                    else:
                        html += '<td style="text-align:center;color:#CCC;">—</td>'
                else:
                    if rec:
                        cl = f"{rec['class_name']} {rec['arm']}"
                        html += (f'<td style="padding:4px;">'
                                 f'<div style="background:#1A56DB;color:white;'
                                 f'border-radius:6px;padding:6px 4px;'
                                 f'text-align:center;line-height:1.4;">'
                                 f'<b>{rec["subject_name"]}</b><br/>'
                                 f'<span style="font-size:9px;">{cl}</span><br/>'
                                 f'<span style="font-size:8px;opacity:.85">'
                                 f'{rec["start_time"]}–{rec["end_time"]}</span>'
                                 f'</div></td>')
                    else:
                        html += ('<td style="text-align:center;color:#38A169;'
                                 'font-weight:700;font-size:10px;">FREE</td>')
            html += '</tr>'
            if slot in special_map:
                sp = special_map[slot]; sp_bg = sp["color_hex"]
                html += (f'<tr><td style="background:{sp_bg};color:white;'
                         f'font-weight:700;padding:5px 8px;'
                         f'text-align:center;">{sp["label"]}</td>')
                for day in present_days:
                    if day in sp["days"].split(","):
                        html += (f'<td style="background:{sp_bg};color:white;'
                                 f'text-align:center;padding:5px;">'
                                 f'<b>{sp["label"]}</b> {sp["duration"]}min</td>')
                    else:
                        html += '<td style="background:#f5f5f5;"></td>'
                html += '</tr>'
        html += '</table>'
        return html

    if view_mode=="By Class":
        classes = get_all_classes()
        if not classes:
            st.info("No classes defined.")
        else:
            cls_opts = {c["id"]: f"{c['name']} {c['arm']} ({c['level']})" for c in classes}
            sel_cls  = st.selectbox("Select Class", list(cls_opts.keys()),
                                    format_func=lambda x: cls_opts[x])
            periods  = get_periods_for_class(sel_cls, sel_ver)
            if not periods:
                st.warning(f"No timetable for this class in '{sel_ver}'.")
            else:
                slot_map     = {(p["day"],p["slot_number"]): p for p in periods}
                present_days = [d for d in DAY_ORDER
                                if any(p["day"]==d for p in periods)]
                st.markdown(render_grid(present_days,slot_map,"class"),
                            unsafe_allow_html=True)
                if not is_version_locked(sel_ver):
                    st.markdown("---")
                    st.subheader("🔀 Swap Two Periods")
                    sw1,sw2,sw3,sw4,sw5 = st.columns(5)
                    with sw1: day_a  = st.selectbox("Day A",  present_days,key="sda")
                    with sw2: slot_a = st.number_input("Slot A",1,periods_per_day,1,key="ssa")
                    with sw3: day_b  = st.selectbox("Day B",  present_days,key="sdb")
                    with sw4: slot_b = st.number_input("Slot B",1,periods_per_day,2,key="ssb")
                    with sw5:
                        st.write(""); st.write("")
                        if st.button("🔀 Swap", width="stretch"):
                            ok, msg = swap_periods(sel_cls, day_a, int(slot_a),
                                                   day_b, int(slot_b), sel_ver)
                            if ok: st.success(msg); st.rerun()
                            else:  st.error(msg)
                else:
                    st.info("🔒 This version is locked. Swaps are disabled.")
    else:
        teachers = get_all_teachers()
        if not teachers:
            st.info("No teachers defined.")
        else:
            teach_opts = {t["id"]: t["name"] for t in teachers}
            sel_t      = st.selectbox("Select Teacher", list(teach_opts.keys()),
                                      format_func=lambda x: teach_opts[x])
            periods    = get_periods_for_teacher(sel_t, sel_ver)
            if not periods:
                st.warning(f"No periods in '{sel_ver}'.")
            else:
                slot_map     = {(p["day"],p["slot_number"]): p for p in periods}
                present_days = [d for d in DAY_ORDER
                                if any(p["day"]==d for p in periods)]
                st.markdown(render_grid(present_days,slot_map,"teacher"),
                            unsafe_allow_html=True)
                st.markdown(f"**{len(periods)} period(s)/week**")


# ════════════════════════════════════════════════════════════════════════════
# 🔍  CLASH DETECTOR
# ════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Clash Detector":
    st.markdown('<div class="page-title">🔍 Clash Detector</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">On-demand scan: teacher double-booking, '
        'class conflicts, under-scheduled subjects</div>', unsafe_allow_html=True)

    versions   = get_all_versions()
    ver_tags   = [v["version_tag"] for v in versions]
    active_ver = get_active_version()
    scan_ver   = st.selectbox("Scan version", ver_tags,
                              index=ver_tags.index(active_ver)
                              if active_ver in ver_tags else 0)

    if st.button("🔍 Run Clash Scan", type="primary", width="stretch"):
        with st.spinner("Scanning…"):
            clashes = detect_clashes(scan_ver)
        log_change("SCAN","clash_detector",
                   f"Scanned {scan_ver} — {len(clashes)} clash(es)")

        if not clashes:
            st.success(f"✅ No clashes in **{scan_ver}**. All constraints satisfied.")
        else:
            high   = [c for c in clashes if c["severity"]=="high"]
            medium = [c for c in clashes if c["severity"]=="medium"]
            ci1,ci2,ci3 = st.columns(3)
            ci1.metric("Total Issues",  len(clashes))
            ci2.metric("High Severity", len(high))
            ci3.metric("Medium",        len(medium))
            st.markdown("---")
            for c in clashes:
                css  = "clash-high" if c["severity"]=="high" else "clash-medium"
                icon = "🔴" if c["severity"]=="high" else "🟡"
                st.markdown(
                    f'<div class="{css}">{icon} <b>{c["type"]}</b>'
                    f'<br/>{c["detail"]}</div>',
                    unsafe_allow_html=True)

        # Also show conflict heatmap if data exists
        periods = get_all_periods(scan_ver)
        if periods:
            st.markdown("---")
            st.subheader("🗓️ Period Utilisation Heatmap")
            hm = get_utilisation_heatmap_df(scan_ver)
            if not hm.empty:
                fig = go.Figure(go.Heatmap(
                    z=hm.values, x=hm.columns.tolist(),
                    y=[f"Slot {i}" for i in hm.index],
                    colorscale="RdYlGn", zmin=0, zmax=1,
                    text=[[f"{v:.0%}" for v in row] for row in hm.values],
                    texttemplate="%{text}", showscale=True))
                fig.update_layout(height=300, margin=dict(l=0,r=0,t=10,b=0),
                                   font=dict(family="Plus Jakarta Sans"))
                st.plotly_chart(fig, width="stretch")


# ════════════════════════════════════════════════════════════════════════════
# 🔄  SUBSTITUTIONS
# ════════════════════════════════════════════════════════════════════════════
elif page == "🔄 Substitutions":
    st.markdown('<div class="page-title">🔄 Substitutions</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Record absences. Auto-suggests '
        'conflict-free substitutes per slot.</div>', unsafe_allow_html=True)

    teachers   = get_all_teachers()
    classes    = get_all_classes()
    subjects   = get_all_subjects()
    active_ver = get_active_version()
    t_opts     = {t["id"]: t["name"] for t in teachers}
    c_opts     = {c["id"]: f"{c['name']} {c['arm']}" for c in classes}
    s_opts     = {s["id"]: s["name"] for s in subjects}
    days_all   = ["Monday","Tuesday","Wednesday","Thursday","Friday"]
    ppd        = int(get_config("periods_per_day",8))

    tab_add, tab_list = st.tabs(["➕ Record Absence","📋 All Substitutions"])

    with tab_add:
        with st.form("add_sub"):
            fc1,fc2 = st.columns(2)
            with fc1:
                abs_date   = st.date_input("Absence Date", date.today())
                absent_tid = st.selectbox("Absent Teacher *",
                                          list(t_opts.keys()),
                                          format_func=lambda x: t_opts[x])
            with fc2:
                abs_day  = st.selectbox("Day", days_all)
                abs_slot = st.number_input("Period Slot",1,ppd,1)
            abs_class   = st.selectbox("Class Affected",
                                       [None]+list(c_opts.keys()),
                                       format_func=lambda x:
                                       "— Select —" if x is None else c_opts[x])
            abs_subject = st.selectbox("Subject",
                                       [None]+list(s_opts.keys()),
                                       format_func=lambda x:
                                       "— Select —" if x is None else s_opts[x])
            reason = st.text_input("Reason (optional)")
            st.markdown("---")
            st.caption(f"**Free substitutes for {abs_day} slot {abs_slot}:**")
            free_t = get_available_substitutes(abs_day, abs_slot, active_ver)
            for ft in free_t:
                st.markdown(f"• {ft['name']} ({ft['staff_type'].title()})")
            if not free_t:
                st.warning("No free teachers at this slot.")
            sub_tid = st.selectbox("Assign Substitute",
                                   [None]+[ft["id"] for ft in free_t],
                                   format_func=lambda x:
                                   "— Assign later —" if x is None
                                   else next(t["name"] for t in free_t
                                             if t["id"]==x))
            if st.form_submit_button("✅ Record Absence", type="primary"):
                add_substitution(
                    abs_date.isoformat(), absent_tid,
                    abs_class, abs_subject, abs_slot, abs_day,
                    sub_tid, reason, active_ver)
                st.success("Recorded!"); st.rerun()

    with tab_list:
        date_filter = st.date_input("Filter by date (clear for all)",
                                    value=None, key="sub_df")
        subs = get_substitutions(
            date_filter.isoformat() if date_filter else None,
            active_ver)
        if not subs:
            st.info("No substitutions recorded.")
        else:
            for s in subs:
                lbl = (f"{s['absence_date']} | {s['day']} Slot {s['slot_number']} | "
                       f"{s['absent_teacher_name']} → "
                       f"{s.get('substitute_teacher_name') or 'Unassigned'}")
                icon = {"pending":"🟡","confirmed":"🟢","cancelled":"🔴"}.get(s["status"],"⚪")
                with st.expander(f"{icon} {lbl}"):
                    st.write(f"**Class:** {s.get('class_name','')} {s.get('arm','')}")
                    st.write(f"**Subject:** {s.get('subject_name','—')}")
                    st.write(f"**Reason:** {s.get('reason','—')}")
                    uc1,uc2,uc3 = st.columns(3)
                    with uc1:
                        new_sub = st.selectbox(
                            "Substitute", [None]+list(t_opts.keys()),
                            index=([None]+list(t_opts.keys()))
                            .index(s["substitute_teacher_id"])
                            if s["substitute_teacher_id"] in t_opts else 0,
                            format_func=lambda x: "— None —"
                            if x is None else t_opts[x],
                            key=f"sub_t_{s['id']}")
                    with uc2:
                        new_status = st.selectbox(
                            "Status",["pending","confirmed","cancelled"],
                            index=["pending","confirmed","cancelled"]
                            .index(s["status"]),
                            key=f"sub_s_{s['id']}")
                    with uc3:
                        st.write("")
                        if st.button("💾 Update", key=f"upd_{s['id']}"):
                            update_substitution_status(s["id"],new_status,new_sub)
                            st.success("Updated!"); st.rerun()
                    if st.button("🗑️ Delete", key=f"del_sub_{s['id']}"):
                        delete_substitution(s["id"]); st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# 📢  NOTICES
# ════════════════════════════════════════════════════════════════════════════
elif page == "📢 Notices":
    st.markdown('<div class="page-title">📢 Notices</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">School-wide or per-class announcements. '
        'Urgent notices appear on the Dashboard.</div>', unsafe_allow_html=True)

    classes  = get_all_classes()
    subjects = get_all_subjects()
    c_opts   = {c["id"]: f"{c['name']} {c['arm']}" for c in classes}
    s_opts   = {s["id"]: s["name"] for s in subjects}
    tab_post, tab_view = st.tabs(["✏️ Post Notice","📋 All Notices"])

    with tab_post:
        with st.form("add_notice"):
            title    = st.text_input("Title *")
            body     = st.text_area("Message *", height=100)
            pc1, pc2 = st.columns(2)
            with pc1:
                target_class = st.selectbox("Target Class",
                                            [None]+list(c_opts.keys()),
                                            format_func=lambda x:
                                            "— All Classes —"
                                            if x is None else c_opts[x])
                priority = st.selectbox("Priority",
                                        ["low","normal","high","urgent"])
            with pc2:
                target_subj = st.selectbox("Related Subject (optional)",
                                           [None]+list(s_opts.keys()),
                                           format_func=lambda x:
                                           "— None —"
                                           if x is None else s_opts[x])
                expires = st.date_input("Expires On (optional)", value=None)
            if st.form_submit_button("📢 Post Notice", type="primary"):
                if not title.strip() or not body.strip():
                    st.error("Title and message required.")
                else:
                    add_notice(title.strip(), body.strip(), target_class,
                               target_subj, priority,
                               expires.isoformat() if expires else None)
                    st.success("Posted!"); st.rerun()

    with tab_view:
        show_exp   = st.checkbox("Include expired")
        filter_cls = st.selectbox("Filter by class",
                                  [None]+list(c_opts.keys()),
                                  format_func=lambda x:
                                  "— All —" if x is None else c_opts[x],
                                  key="nf")
        notices = get_notices(class_id=filter_cls, include_expired=show_exp)
        if not notices:
            st.info("No notices.")
        else:
            p_colors = {"urgent":"notice-urgent","high":"notice-high",
                        "normal":"notice-normal","low":"notice-low"}
            p_icons  = {"urgent":"🚨","high":"⚠️","normal":"📢","low":"💬"}
            for n in notices:
                css  = p_colors.get(n["priority"],"notice-normal")
                icon = p_icons.get(n["priority"],"📢")
                cl   = (f"{n.get('class_name','')} {n.get('arm','')}"
                        if n.get("class_name") else "All Classes")
                ts   = str(n["created_at"])[:16]
                exp  = f" · Expires {n['expires_on']}" if n.get("expires_on") else ""
                st.markdown(
                    f'<div class="{css}">{icon} '
                    f'<b style="font-size:14px;">{n["title"]}</b> '
                    f'<span style="font-size:10px;color:#718096;">'
                    f'{cl} · {ts}{exp}</span><br/>'
                    f'<span style="font-size:13px;">{n["body"]}</span></div>',
                    unsafe_allow_html=True)
                if st.button("🗑️ Delete", key=f"dn_{n['id']}"):
                    delete_notice(n["id"]); st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# 📝  EXAM TIMETABLE
# ════════════════════════════════════════════════════════════════════════════
elif page == "📝 Exam Timetable":
    st.markdown('<div class="page-title">📝 Exam Timetable</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Schedule exams with dates, times, venues '
        'and invigilators. Clash detection included.</div>',
        unsafe_allow_html=True)

    teachers = get_all_teachers()
    classes  = get_all_classes()
    subjects = get_all_subjects()
    t_opts   = {t["id"]: t["name"] for t in teachers}
    c_opts   = {c["id"]: f"{c['name']} {c['arm']}" for c in classes}
    s_opts   = {s["id"]: s["name"] for s in subjects}
    curr_session = get_config("current_session","2024/2025")
    curr_term    = get_config("current_term","First Term")

    tab_add, tab_view, tab_pdf = st.tabs([
        "➕ Add Exam Slot","📋 View Schedule","📄 PDF Export"])

    with tab_add:
        with st.form("add_exam"):
            ec1, ec2 = st.columns(2)
            with ec1:
                e_date    = st.date_input("Exam Date *", date.today())
                e_subject = st.selectbox("Subject *",
                                         list(s_opts.keys()),
                                         format_func=lambda x: s_opts[x])
                e_venue   = st.text_input("Venue",placeholder="Hall A, Classroom 3")
            with ec2:
                e_start   = st.text_input("Start Time *","09:00")
                e_end     = st.text_input("End Time *","11:00")
                e_invigil = st.selectbox("Invigilator",
                                         [None]+list(t_opts.keys()),
                                         format_func=lambda x:
                                         "— Unassigned —"
                                         if x is None else t_opts[x])
            e_class = st.selectbox("Class *", list(c_opts.keys()),
                                   format_func=lambda x: c_opts[x])
            e_notes = st.text_input("Notes (optional)")
            if st.form_submit_button("✅ Add Exam Slot", type="primary"):
                if not e_date or not e_start or not e_end:
                    st.error("Date, start time, and end time required.")
                else:
                    add_exam_slot(
                        e_date.isoformat(), e_start, e_end,
                        e_subject, e_class, e_venue, e_invigil,
                        e_notes, curr_session, curr_term)
                    st.success("Exam slot added!"); st.rerun()

    with tab_view:
        exam_slots = get_exam_slots(curr_session, curr_term)
        if not exam_slots:
            st.info("No exams scheduled yet.")
        else:
            # Clash check
            clashes = get_exam_clash_report(curr_session, curr_term)
            if clashes:
                st.warning(f"⚠️ {len(clashes)} exam clash(es) detected:")
                for c in clashes:
                    icon = "🔴" if c["severity"]=="high" else "🟡"
                    st.markdown(
                        f'<div class="clash-high">{icon} '
                        f'<b>{c["type"]}</b><br/>{c["detail"]}</div>',
                        unsafe_allow_html=True)
                st.markdown("---")

            df = pd.DataFrame(exam_slots)[[
                "exam_date","start_time","end_time",
                "subject_name","class_name","arm","venue","invigilator_name"]]
            df.columns = ["Date","Start","End","Subject",
                          "Class","Arm","Venue","Invigilator"]
            st.dataframe(df, width="stretch", hide_index=True)

            st.markdown("---")
            for e in exam_slots:
                lbl = (f"{e['exam_date']} {e['start_time']}–{e['end_time']} | "
                       f"{e['subject_name']} | {e['class_name']} {e['arm']}")
                with st.expander(lbl):
                    st.write(f"**Venue:** {e.get('venue','—')}")
                    st.write(f"**Invigilator:** {e.get('invigilator_name','—')}")
                    st.write(f"**Notes:** {e.get('notes','—')}")
                    if st.button("🗑️ Delete", key=f"del_e_{e['id']}"):
                        delete_exam_slot(e["id"]); st.rerun()

    with tab_pdf:
        exam_slots = get_exam_slots(curr_session, curr_term)
        st.caption(f"Generates PDF for {curr_term} {curr_session}")
        if st.button("📄 Download Exam Timetable PDF",
                     type="primary", width="stretch",
                     disabled=not exam_slots):
            with st.spinner("Building PDF…"):
                pdf = export_exam_timetable_pdf(
                    exam_slots,
                    get_config("school_name","HMG Academy"),
                    curr_term, curr_session)
            st.download_button(
                "⬇️ exam_timetable.pdf", pdf,
                "exam_timetable.pdf","application/pdf",
                width="stretch")
        if not exam_slots:
            st.info("Add exam slots first.")


# ════════════════════════════════════════════════════════════════════════════
# 📅  TERM CALENDAR
# ════════════════════════════════════════════════════════════════════════════
elif page == "📅 Term Calendar":
    st.markdown('<div class="page-title">📅 Term Calendar</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Mark public holidays, closures and school events. '
        'Holidays are respected by the timetable engine.</div>',
        unsafe_allow_html=True)

    classes = get_all_classes()
    c_opts  = {c["id"]: f"{c['name']} {c['arm']}" for c in classes}
    tab_add, tab_view = st.tabs(["➕ Add Event","📋 Calendar"])

    with tab_add:
        with st.form("add_cal"):
            cal_c1, cal_c2 = st.columns(2)
            with cal_c1:
                ev_date  = st.date_input("Date *", date.today())
                ev_title = st.text_input("Event Title *",
                                         placeholder="Independence Day, End of Term…")
            with cal_c2:
                ev_type = st.selectbox("Event Type",
                                       ["holiday","event","exam","closure"])
                ev_all  = st.checkbox("Affects All Classes", value=True)
            ev_desc    = st.text_area("Description (optional)", height=60)
            ev_class   = None
            if not ev_all:
                ev_class = st.selectbox("Specific Class",
                                        list(c_opts.keys()),
                                        format_func=lambda x: c_opts[x])
            if st.form_submit_button("✅ Add to Calendar", type="primary"):
                if not ev_title.strip():
                    st.error("Title required.")
                else:
                    add_calendar_event(
                        ev_date.isoformat(), ev_title.strip(),
                        ev_type, ev_desc, ev_all, ev_class)
                    st.success("Added!"); st.rerun()

    with tab_view:
        cal_c1, cal_c2 = st.columns(2)
        with cal_c1:
            view_month = st.selectbox("Month",
                                      list(range(1,13)),
                                      index=date.today().month-1,
                                      format_func=lambda m:
                                      date(2000,m,1).strftime("%B"))
        with cal_c2:
            view_year = st.number_input("Year",2020,2035,
                                        value=date.today().year)

        events = get_calendar_events(view_month, view_year)
        if not events:
            st.info(f"No events in {date(2000,view_month,1).strftime('%B')} {view_year}.")
        else:
            type_css = {"holiday":"cal-holiday","event":"cal-event",
                        "exam":"cal-exam","closure":"cal-closure"}
            type_icon= {"holiday":"🏖️","event":"📌","exam":"📝","closure":"🚫"}
            for ev in events:
                css  = type_css.get(ev["event_type"],"cal-event")
                icon = type_icon.get(ev["event_type"],"📌")
                cl   = (f"{ev.get('class_name','')} {ev.get('arm','')}".strip()
                        if ev.get("class_name") else "All Classes")
                st.markdown(
                    f'<div class="{css}">{icon} '
                    f'<b>{ev["event_date"]}</b> — '
                    f'<b>{ev["title"]}</b> '
                    f'<span style="font-size:11px;color:#718096;">'
                    f'[{ev["event_type"].upper()}] · {cl}</span>'
                    f'{"<br/><span style=font-size:12px>" + ev["description"] + "</span>" if ev["description"] else ""}'
                    f'</div>',
                    unsafe_allow_html=True)
                if st.button("🗑️", key=f"del_cal_{ev['id']}"):
                    delete_calendar_event(ev["id"]); st.rerun()

        # Summary of all holidays
        all_holidays = get_holiday_dates()
        if all_holidays:
            st.markdown("---")
            st.caption(f"**Total holidays/closures on record: {len(all_holidays)}** "
                       f"(timetable engine avoids scheduling on these dates)")


# ════════════════════════════════════════════════════════════════════════════
# 📊  STATISTICS
# ════════════════════════════════════════════════════════════════════════════
elif page == "📊 Statistics":
    st.markdown('<div class="page-title">📊 Statistics</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Subject analytics, teacher utilisation, PDF report</div>',
                unsafe_allow_html=True)

    versions   = get_all_versions()
    ver_tags   = [v["version_tag"] for v in versions]
    active_ver = get_active_version()
    stat_ver   = st.selectbox("Version to analyse", ver_tags,
                              index=ver_tags.index(active_ver)
                              if active_ver in ver_tags else 0)

    st.subheader("📚 Subject Period Distribution")
    dist = get_subject_distribution(stat_ver)
    if dist:
        dist_df = pd.DataFrame(dist)
        fig = px.bar(dist_df, x="subject_name", y="total_periods",
                     color="total_periods", color_continuous_scale="Viridis",
                     hover_data=["teacher_name","classes_count"],
                     labels={"subject_name":"Subject","total_periods":"Periods"})
        fig.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=0),
                           showlegend=False, coloraxis_showscale=False,
                           font=dict(family="Plus Jakarta Sans"),
                           plot_bgcolor="white", paper_bgcolor="white")
        fig.update_xaxes(tickangle=-30, tickfont=dict(size=9))
        st.plotly_chart(fig, width="stretch")
        st.dataframe(
            dist_df.rename(columns={
                "subject_name":"Subject","teacher_name":"Teacher",
                "total_periods":"Total Periods","classes_count":"Classes"}),
            width="stretch", hide_index=True)
    else:
        st.info("No data for this version.")

    st.markdown("---")
    st.subheader("👩‍🏫 Teacher Workload")
    wl = get_teacher_workload_df(stat_ver)
    if not wl.empty:
        fig2 = px.bar(wl, x="teacher", y="periods",
                      color="periods", color_continuous_scale="Blues")
        fig2.update_layout(height=260, margin=dict(l=0,r=0,t=10,b=0),
                            showlegend=False, coloraxis_showscale=False,
                            font=dict(family="Plus Jakarta Sans"),
                            plot_bgcolor="white", paper_bgcolor="white")
        fig2.update_xaxes(tickangle=-30, tickfont=dict(size=9))
        st.plotly_chart(fig2, width="stretch")

    st.subheader("👨‍🎓 Class Sizes")
    size_stats = get_class_size_stats()
    if any(s["student_count"] > 0 for s in size_stats):
        sz_df = pd.DataFrame(size_stats)
        sz_df["label"] = sz_df["class_name"]+" "+sz_df["arm"]
        fig4 = px.bar(sz_df, x="label", y="student_count",
                      color="level",
                      color_discrete_map={"JSS":"#1A56DB","SSS":"#E74C3C"})
        fig4.update_layout(height=240, margin=dict(l=0,r=0,t=10,b=0),
                            font=dict(family="Plus Jakarta Sans"),
                            plot_bgcolor="white", paper_bgcolor="white")
        fig4.update_xaxes(tickangle=-30, tickfont=dict(size=9))
        st.plotly_chart(fig4, width="stretch")

    st.markdown("---")
    if st.button("📄 Download Statistics Report PDF",
                 width="stretch"):
        with st.spinner("Building…"):
            pdf = export_statistics_report(stat_ver)
        st.download_button("⬇️ statistics_report.pdf", pdf,
                           "statistics_report.pdf","application/pdf",
                           width="stretch")


# ════════════════════════════════════════════════════════════════════════════
# 📋  CHANGE LOG
# ════════════════════════════════════════════════════════════════════════════
elif page == "📋 Change Log":
    st.markdown('<div class="page-title">📋 Change Log</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Full audit trail of every action</div>',
                unsafe_allow_html=True)

    limit = st.slider("Show last N entries",20,500,100)
    logs  = get_change_log(limit)

    if not logs:
        st.info("No activity yet.")
    else:
        st.caption(f"Showing {len(logs)} most recent entries")
        action_colors = {
            "CREATE":"#38A169","UPDATE":"#1A56DB","DELETE":"#E53E3E",
            "GENERATE":"#8E44AD","SWAP":"#F5A623","SCAN":"#16A085",
            "BULK":"#D69E2E","IMPORT":"#2980B9","LOCK":"#E53E3E",
            "UNLOCK":"#38A169",
        }
        for log in logs:
            color = action_colors.get(log["action"],"#718096")
            ts    = str(log["created_at"])[:19].replace("T"," ")
            st.markdown(
                f'<div class="log-row">'
                f'<span style="background:{color};color:white;border-radius:4px;'
                f'padding:1px 7px;font-size:10px;font-weight:700;">'
                f'{log["action"]}</span> '
                f'<b style="font-size:12px;">{log["entity"]}</b> — '
                f'<span style="font-size:12px;">{log["description"]}</span>'
                f'<span style="color:#A0AEC0;float:right;font-size:11px;">'
                f'{ts}</span></div>',
                unsafe_allow_html=True)

        st.markdown("---")
        cl1, cl2 = st.columns(2)
        with cl1:
            if st.button("🗑️ Clear Log", type="secondary",
                         width="stretch"):
                clear_change_log()
                st.success("Cleared."); st.rerun()
        with cl2:
            if st.button("📊 Download as CSV", width="stretch"):
                df  = pd.DataFrame(logs)
                csv = df.to_csv(index=False).encode()
                st.download_button("⬇️ change_log.csv", csv,
                                   "change_log.csv","text/csv",
                                   width="stretch")


# ════════════════════════════════════════════════════════════════════════════
# 📤  EXPORT
# ════════════════════════════════════════════════════════════════════════════
elif page == "📤 Export":
    st.markdown('<div class="page-title">📤 Export</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">All PDF and CSV downloads in one place</div>',
                unsafe_allow_html=True)

    versions   = get_all_versions()
    ver_tags   = [v["version_tag"] for v in versions]
    active_ver = get_active_version()
    classes    = get_all_classes()
    teachers   = get_all_teachers()

    exp_ver = st.selectbox("Export from version", ver_tags,
                           index=ver_tags.index(active_ver)
                           if active_ver in ver_tags else 0,
                           key="exp_ver")
    periods_in_ver = len(get_all_periods(exp_ver))
    if periods_in_ver == 0:
        st.warning(f"Version '{exp_ver}' has no data. Generate first.")

    # ── Class Timetable PDF ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🏫 Class Timetable PDF")
    ec1, ec2 = st.columns(2)
    with ec1:
        if st.button("📄 All Classes (Landscape)",
                     width="stretch", disabled=periods_in_ver==0):
            with st.spinner("Building…"):
                pdf = export_class_timetable_pdf(version=exp_ver)
            st.download_button("⬇️ all_classes_timetable.pdf", pdf,
                               "all_classes_timetable.pdf","application/pdf",
                               width="stretch")
    with ec2:
        if classes:
            cls_sel = st.selectbox("Compact (A4 Portrait) — select class",
                                   [c["id"] for c in classes],
                                   format_func=lambda x:
                                   next(f"{c['name']} {c['arm']}"
                                        for c in classes if c["id"]==x),
                                   key="compact_cls")
            if st.button("🖨️ Compact Print PDF",
                         width="stretch", disabled=periods_in_ver==0):
                with st.spinner("Building…"):
                    pdf = export_compact_timetable_pdf(cls_sel, version=exp_ver)
                fname = next(f"{c['name']}_{c['arm']}"
                             for c in classes if c["id"]==cls_sel)
                st.download_button(f"⬇️ {fname}_compact.pdf", pdf,
                                   f"{fname}_compact.pdf","application/pdf",
                                   width="stretch")

    # ── Teacher PDF ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("👩‍🏫 Teacher Timetable PDF")
    et1, et2 = st.columns(2)
    with et1:
        if st.button("📄 All Teachers",
                     width="stretch", disabled=periods_in_ver==0):
            with st.spinner("Building…"):
                pdf = export_teacher_timetable_pdf(version=exp_ver)
            st.download_button("⬇️ all_teachers_timetable.pdf", pdf,
                               "all_teachers_timetable.pdf","application/pdf",
                               width="stretch")
    with et2:
        if teachers:
            tea_sel = st.selectbox("Teacher Report Card",
                                   [t["id"] for t in teachers],
                                   format_func=lambda x:
                                   next(t["name"] for t in teachers if t["id"]==x),
                                   key="rep_tea")
            if st.button("📄 Teacher Report PDF",
                         width="stretch", disabled=periods_in_ver==0):
                with st.spinner("Building…"):
                    t_rec    = next(t for t in teachers if t["id"]==tea_sel)
                    t_periods= get_periods_for_teacher(tea_sel, exp_ver)
                    pdf = export_teacher_report_pdf(t_rec, t_periods, exp_ver)
                fname = t_rec["name"].replace(" ","_")
                st.download_button(f"⬇️ {fname}_report.pdf", pdf,
                                   f"{fname}_report.pdf","application/pdf",
                                   width="stretch")

    # ── Student Register ───────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("👨‍🎓 Student Register PDF")
    if classes:
        reg_cls = st.selectbox("Select class for register",
                               [c["id"] for c in classes],
                               format_func=lambda x:
                               next(f"{c['name']} {c['arm']}"
                                    for c in classes if c["id"]==x),
                               key="reg_cls_exp")
        students = get_students_for_class(reg_cls)
        st.caption(f"{len(students)} students in this class")
        if st.button("📄 Download Register PDF",
                     width="stretch", disabled=not students):
            with st.spinner("Building…"):
                pdf = export_student_register_pdf(reg_cls, students)
            fname = next(f"{c['name']}_{c['arm']}"
                         for c in classes if c["id"]==reg_cls)
            st.download_button(f"⬇️ {fname}_register.pdf", pdf,
                               f"{fname}_register.pdf","application/pdf",
                               width="stretch")
        if not students:
            st.info("Add students to this class first.")

    # ── Exam Timetable PDF ─────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📝 Exam Timetable PDF")
    curr_session = get_config("current_session","2024/2025")
    curr_term    = get_config("current_term","First Term")
    exam_slots   = get_exam_slots(curr_session, curr_term)
    st.caption(f"Exports exam schedule for {curr_term} {curr_session}")
    if st.button("📄 Download Exam Timetable PDF",
                 width="stretch", disabled=not exam_slots):
        with st.spinner("Building…"):
            pdf = export_exam_timetable_pdf(
                exam_slots,
                get_config("school_name","HMG Academy"),
                curr_term, curr_session)
        st.download_button("⬇️ exam_timetable.pdf", pdf,
                           "exam_timetable.pdf","application/pdf",
                           width="stretch")

    # ── Statistics Report ──────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 Statistics Report PDF")
    if st.button("📊 Download Statistics Report",
                 width="stretch", disabled=periods_in_ver==0):
        with st.spinner("Building…"):
            pdf = export_statistics_report(exp_ver)
        st.download_button("⬇️ statistics_report.pdf", pdf,
                           "statistics_report.pdf","application/pdf",
                           width="stretch")

    # ── Generation Report ──────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📄 Generation Report PDF")
    if "last_report_data" in st.session_state:
        if st.button("📄 Download Last Generation Report",
                     width="stretch"):
            with st.spinner("Building…"):
                pdf = export_generation_report(
                    st.session_state["last_report_data"])
            st.download_button("⬇️ generation_report.pdf", pdf,
                               "generation_report.pdf","application/pdf",
                               width="stretch")
    else:
        st.info("Run Generate Timetable first.")

    # ── Master CSV ─────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📋 Master CSV")
    if st.button("📋 Download Master CSV",
                 width="stretch", disabled=periods_in_ver==0):
        with st.spinner("Exporting…"):
            csv_bytes = export_master_csv(exp_ver)
        st.download_button(f"⬇️ {exp_ver}_master_timetable.csv",
                           csv_bytes,
                           f"{exp_ver}_master_timetable.csv","text/csv",
                           width="stretch")


# ════════════════════════════════════════════════════════════════════════════
# Global footer — always visible at the bottom of every page
# ════════════════════════════════════════════════════════════════════════════
st.markdown(
    f"""
    <hr style="margin-top:48px;margin-bottom:8px;border:none;
               border-top:1px solid #E5EAF2;">
    <div style="text-align:center;color:#94A3B8;font-size:11px;
                padding:6px 0 18px;line-height:1.6;">
      <div>
        <b style="color:#475569;">{B.PRODUCT_NAME}</b> {B.PRODUCT_VERSION} —
        a product of
        <a href="{B.URL_CONCEPTS}" target="_blank"
           style="color:{B.COLOR_PRIMARY};text-decoration:none;">{B.VENDOR}</a>,
        the EdTech arm of
        <a href="{B.URL_CONCEPTS}" target="_blank"
           style="color:{B.COLOR_PRIMARY};text-decoration:none;">{B.PARENT_BRAND}</a>.
      </div>
      <div style="margin-top:3px;">
        Engineered by
        <a href="{B.URL_FOUNDER}" target="_blank"
           style="color:{B.COLOR_PRIMARY};text-decoration:none;">
           {B.FOUNDER_NAME}</a>
        · {B.LOCATION} · Est. {B.FOUNDED_YEAR}
      </div>
      <div style="margin-top:3px;font-style:italic;color:#A0AEC0;">
        "{B.PARENT_TAGLINE}"
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
