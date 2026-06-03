"""
================================================================================
TimetableCraft — pdf_gen.py  (v2)
Timetable PDF Exporter (ReportLab)
HMG Concepts | AI-Augmented Solutions
================================================================================
v2 additions:
  - Special slot rows (Assembly, Break, Lunch) in class + teacher PDFs
  - export_generation_report(): one-page post-generation summary PDF
    · School name, term, session, version
    · Periods assigned, conflict count, classes, subjects
    · Teacher load table
    · Conflict list (if any)
================================================================================
"""

import io
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, PageBreak, KeepTogether
)

from db import (
    get_all_classes, get_all_teachers, get_all_periods,
    get_periods_for_class, get_periods_for_teacher,
    get_all_special_slots, get_config, get_active_version
)

DAY_ORDER   = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
OUTPUT_DIR  = Path("exports")
OUTPUT_DIR.mkdir(exist_ok=True)

# Brand palette
BRAND_DARK  = colors.HexColor("#0F1923")
BRAND_BLUE  = colors.HexColor("#1A56DB")
BRAND_LIGHT = colors.HexColor("#F0F4FF")
BRAND_GOLD  = colors.HexColor("#F5A623")
HEADER_BG   = colors.HexColor("#1E2B3C")
ALT_ROW     = colors.HexColor("#EBF0FA")
EMPTY_CELL  = colors.HexColor("#F7F9FC")
SUCCESS_GRN = colors.HexColor("#38A169")
DANGER_RED  = colors.HexColor("#E53E3E")


def hex_to_rl(hex_str):
    try:
        return colors.HexColor(hex_str)
    except Exception:
        return BRAND_BLUE


def _ordinal(n):
    sfx = {1:"st",2:"nd",3:"rd"}.get(
        n % 10 if n % 100 not in (11,12,13) else 0, "th")
    return f"{n}{sfx}"


def _page_footer(canvas, doc, title, school_name):
    """Two-line PDF footer carrying both the school's name and the
    TimetableCraft / HMG Technologies attribution on every page."""
    canvas.saveState()
    w, h = doc.pagesize
    canvas.setFillColor(BRAND_DARK)
    canvas.rect(0, 0, w, 1.4*cm, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.setFillColor(colors.white)
    canvas.drawString(1*cm, 0.78*cm,
        f"{school_name}  ·  TimetableCraft — {title}")
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(colors.HexColor("#B8C7DD"))
    canvas.drawString(1*cm, 0.30*cm,
        "Powered by TimetableCraft · HMG Technologies (a subsidiary of HMG Concepts) "
        "· Engineered by Adewale Samson Adeagbo · hmgconcepts.pages.dev")
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(w - 1*cm, 0.78*cm, f"Page {doc.page}")
    canvas.restoreState()


# ══════════════════════════════════════════════════════════════════════════════
# Shared: Build timetable table rows (with special slot interleaving)
# ══════════════════════════════════════════════════════════════════════════════
def _build_grid_rows(present_days, periods_per_day, slot_map,
                     cell_style, small_style, mode="class"):
    """
    Build table data rows interleaving special slot rows (Assembly, Break).
    mode: 'class' colours by subject; 'teacher' uses uniform blue / FREE labels.
    Returns (table_data_rows, table_style_commands, color_map)
    where color_map is {(row_index, col_index): hex_str} for post-processing.
    """
    specials = get_all_special_slots()
    # position→label map
    special_map: Dict[int, dict] = {}
    for s in specials:
        special_map[int(s["position"])] = s

    rows      = []
    style_cmds = []
    color_map  = {}   # (row_idx_in_table, col_idx) → color hex
    row_cursor = 0    # tracks actual row index in the full table (excl header)

    # Assembly row (position 0 → before slot 1)
    if 0 in special_map:
        sp = special_map[0]
        sp_days = set(sp["days"].split(","))
        sp_row  = [Paragraph(f"<b>{sp['label']}</b>", small_style)]
        for day in present_days:
            if day in sp_days:
                sp_row.append(Paragraph(
                    f"<b>{sp['label']}</b><br/>"
                    f"<font size='6'>{sp['duration']} min</font>",
                    small_style
                ))
            else:
                sp_row.append(Paragraph("", small_style))
        rows.append(sp_row)
        # Style the whole special row
        ri = row_cursor + 1   # +1 for header
        style_cmds += [
            ("BACKGROUND", (0, ri), (-1, ri), hex_to_rl(sp["color_hex"])),
            ("TEXTCOLOR",  (0, ri), (-1, ri), colors.white),
            ("FONTNAME",   (0, ri), (-1, ri), "Helvetica-BoldOblique"),
        ]
        row_cursor += 1

    for slot in range(1, periods_per_day + 1):
        # Period row
        row = [Paragraph(f"<b>{_ordinal(slot)}</b>", cell_style)]
        for col_i, day in enumerate(present_days, start=1):
            rec = slot_map.get((day, slot))
            ri  = row_cursor + 1   # +1 for header

            if mode == "class":
                if rec and rec.get("subject_name"):
                    t_range = f"{rec['start_time']}–{rec['end_time']}"
                    dbl     = " 🔁" if rec.get("is_double") else ""
                    row.append(Paragraph(
                        f"<b>{rec['subject_name']}{dbl}</b><br/>"
                        f"{rec.get('teacher_name','')}<br/>"
                        f"<font size='5'>{t_range}</font>",
                        cell_style
                    ))
                    color_map[(ri, col_i)] = rec.get("color_hex", "#4A90D9")
                else:
                    row.append(Paragraph("—", small_style))
            else:  # teacher mode
                if rec:
                    cl = f"{rec['class_name']} {rec['arm']}"
                    row.append(Paragraph(
                        f"<b>{rec['subject_name']}</b><br/>{cl}<br/>"
                        f"<font size='5'>{rec['start_time']}–{rec['end_time']}</font>",
                        cell_style
                    ))
                    color_map[(ri, col_i)] = "#1A56DB"
                else:
                    row.append(Paragraph("FREE", ParagraphStyle(
                        "free", fontSize=7, textColor=colors.HexColor("#38A169"),
                        alignment=TA_CENTER, fontName="Helvetica-Bold"
                    )))

        rows.append(row)
        row_cursor += 1

        # Break / Lunch row after this slot?
        if slot in special_map:
            sp    = special_map[slot]
            sp_days = set(sp["days"].split(","))
            sp_row = [Paragraph(f"<b>{sp['label']}</b>", small_style)]
            for day in present_days:
                if day in sp_days:
                    sp_row.append(Paragraph(
                        f"<b>{sp['label']}</b><br/>"
                        f"<font size='6'>{sp['duration']} min</font>",
                        small_style
                    ))
                else:
                    sp_row.append(Paragraph("", small_style))
            rows.append(sp_row)
            ri = row_cursor + 1
            style_cmds += [
                ("BACKGROUND", (0, ri), (-1, ri), hex_to_rl(sp["color_hex"])),
                ("TEXTCOLOR",  (0, ri), (-1, ri), colors.white),
                ("FONTNAME",   (0, ri), (-1, ri), "Helvetica-BoldOblique"),
            ]
            row_cursor += 1

    return rows, style_cmds, color_map


# ══════════════════════════════════════════════════════════════════════════════
# 1. Class Timetable PDF
# ══════════════════════════════════════════════════════════════════════════════
def export_class_timetable_pdf(class_id=None, version=None) -> bytes:
    school_name     = get_config("school_name", "HMG Academy")
    term            = get_config("current_term", "First Term")
    session         = get_config("current_session", "2024/2025")
    periods_per_day = int(get_config("periods_per_day", 8))
    ver             = version or get_active_version()

    classes = get_all_classes() if class_id is None else [
        c for c in get_all_classes() if c["id"] == class_id
    ]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm,
                            title="Class Timetable")

    title_sty  = ParagraphStyle("t_t", fontSize=15, fontName="Helvetica-Bold",
                                 textColor=BRAND_DARK, alignment=TA_CENTER, spaceAfter=3)
    sub_sty    = ParagraphStyle("t_s", fontSize=9, fontName="Helvetica",
                                 textColor=colors.HexColor("#555"), alignment=TA_CENTER,
                                 spaceAfter=10)
    cell_sty   = ParagraphStyle("t_c", fontSize=7, fontName="Helvetica-Bold",
                                 alignment=TA_CENTER, leading=9)
    small_sty  = ParagraphStyle("t_sm", fontSize=6, fontName="Helvetica",
                                 alignment=TA_CENTER, leading=8)

    story = []

    for i, cls in enumerate(classes):
        class_label = f"{cls['name']} {cls['arm']}"
        periods     = get_periods_for_class(cls["id"], ver)
        slot_map    = {(p["day"], p["slot_number"]): p for p in periods}
        present_days = [d for d in DAY_ORDER if any(p["day"]==d for p in periods)] \
                       or DAY_ORDER[:5]

        story.append(Paragraph(school_name, title_sty))
        story.append(Paragraph(
            f"Class Timetable — {class_label} ({cls['level']}) · "
            f"{term} · {session} · {ver}", sub_sty))

        header = ["Period"] + present_days
        body_rows, extra_cmds, color_map = _build_grid_rows(
            present_days, periods_per_day, slot_map,
            cell_sty, small_sty, mode="class"
        )
        table_data = [header] + body_rows

        pw        = landscape(A4)[0] - 3*cm
        day_w     = (pw - 2.2*cm) / len(present_days)
        col_widths = [2.2*cm] + [day_w]*len(present_days)

        tbl = Table(table_data, colWidths=col_widths)
        ts  = TableStyle([
            ("BACKGROUND", (0,0), (-1,0), HEADER_BG),
            ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,0), 9),
            ("ALIGN",      (0,0), (-1,-1), "CENTER"),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, ALT_ROW]),
            ("GRID",       (0,0), (-1,-1), 0.4, colors.HexColor("#CCC")),
            ("LINEBELOW",  (0,0), (-1,0), 2, BRAND_GOLD),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ])
        for cmd in extra_cmds:
            ts.add(*cmd)
        for (ri, ci), hex_c in color_map.items():
            ts.add("BACKGROUND", (ci, ri), (ci, ri), hex_to_rl(hex_c))
            ts.add("TEXTCOLOR",  (ci, ri), (ci, ri), colors.white)
        tbl.setStyle(ts)
        story.append(tbl)
        if i < len(classes)-1:
            story.append(PageBreak())

    doc.build(story,
              onFirstPage=lambda c,d: _page_footer(c,d,"Class Timetable",school_name),
              onLaterPages=lambda c,d: _page_footer(c,d,"Class Timetable",school_name))
    buf.seek(0)
    print(f"[pdf] ✅ Class timetable PDF: {len(classes)} class(es)")
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# 2. Teacher Timetable PDF
# ══════════════════════════════════════════════════════════════════════════════
def export_teacher_timetable_pdf(teacher_id=None, version=None) -> bytes:
    school_name     = get_config("school_name", "HMG Academy")
    term            = get_config("current_term", "First Term")
    session         = get_config("current_session", "2024/2025")
    periods_per_day = int(get_config("periods_per_day", 8))
    ver             = version or get_active_version()

    teachers = get_all_teachers() if teacher_id is None else [
        t for t in get_all_teachers() if t["id"] == teacher_id
    ]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm,
                            title="Teacher Timetable")

    title_sty = ParagraphStyle("tt_t", fontSize=14, fontName="Helvetica-Bold",
                                textColor=BRAND_DARK, alignment=TA_CENTER, spaceAfter=3)
    sub_sty   = ParagraphStyle("tt_s", fontSize=9, fontName="Helvetica",
                                textColor=colors.HexColor("#555"), alignment=TA_CENTER,
                                spaceAfter=10)
    cell_sty  = ParagraphStyle("tt_c", fontSize=7.5, fontName="Helvetica-Bold",
                                alignment=TA_CENTER, leading=9)
    small_sty = ParagraphStyle("tt_sm", fontSize=6, fontName="Helvetica",
                                alignment=TA_CENTER, leading=8)

    story = []

    for i, teacher in enumerate(teachers):
        periods  = get_periods_for_teacher(teacher["id"], ver)
        slot_map = {(p["day"], p["slot_number"]): p for p in periods}
        present_days = [d for d in DAY_ORDER if any(p["day"]==d for p in periods)] \
                       or DAY_ORDER[:5]

        story.append(Paragraph(school_name, title_sty))
        story.append(Paragraph(
            f"Personal Timetable — {teacher['name']} ({teacher['staff_type'].title()}) · "
            f"{len(periods)} periods/week · {term} · {session}", sub_sty))

        header = ["Period"] + present_days
        body_rows, extra_cmds, color_map = _build_grid_rows(
            present_days, periods_per_day, slot_map,
            cell_sty, small_sty, mode="teacher"
        )
        table_data = [header] + body_rows

        pw         = landscape(A4)[0] - 3*cm
        day_w      = (pw - 2.2*cm) / len(present_days)
        col_widths = [2.2*cm] + [day_w]*len(present_days)

        tbl = Table(table_data, colWidths=col_widths)
        ts  = TableStyle([
            ("BACKGROUND", (0,0), (-1,0), HEADER_BG),
            ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,0), 9),
            ("ALIGN",      (0,0), (-1,-1), "CENTER"),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, ALT_ROW]),
            ("GRID",       (0,0), (-1,-1), 0.4, colors.HexColor("#CCC")),
            ("LINEBELOW",  (0,0), (-1,0), 2, BRAND_GOLD),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ])
        for cmd in extra_cmds:
            ts.add(*cmd)
        for (ri, ci), hex_c in color_map.items():
            ts.add("BACKGROUND", (ci, ri), (ci, ri), hex_to_rl(hex_c))
            ts.add("TEXTCOLOR",  (ci, ri), (ci, ri), colors.white)
        tbl.setStyle(ts)
        story.append(tbl)
        if i < len(teachers)-1:
            story.append(PageBreak())

    doc.build(story,
              onFirstPage=lambda c,d: _page_footer(c,d,"Teacher Timetable",school_name),
              onLaterPages=lambda c,d: _page_footer(c,d,"Teacher Timetable",school_name))
    buf.seek(0)
    print(f"[pdf] ✅ Teacher timetable PDF: {len(teachers)} teacher(s)")
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# 3. Post-Generation Report PDF
# ══════════════════════════════════════════════════════════════════════════════
def export_generation_report(report_data: dict) -> bytes:
    """
    One-page post-generation summary PDF.
    report_data is produced by scheduler.build_report_data().
    """
    school_name = report_data.get("school_name", "HMG Academy")
    term        = report_data.get("term", "First Term")
    session     = report_data.get("session", "2024/2025")
    version     = report_data.get("version", "v1")
    success     = report_data.get("success", False)
    generated   = datetime.now().strftime("%d %B %Y, %H:%M")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2.5*cm, bottomMargin=2*cm,
                            title="Generation Report")

    h1  = ParagraphStyle("r_h1", fontSize=20, fontName="Helvetica-Bold",
                          textColor=BRAND_DARK, spaceAfter=4)
    h2  = ParagraphStyle("r_h2", fontSize=13, fontName="Helvetica-Bold",
                          textColor=BRAND_BLUE, spaceBefore=14, spaceAfter=6)
    sub = ParagraphStyle("r_sub", fontSize=10, fontName="Helvetica",
                          textColor=colors.HexColor("#555"), spaceAfter=16)
    body= ParagraphStyle("r_body", fontSize=9, fontName="Helvetica",
                          textColor=BRAND_DARK, spaceAfter=4)
    ok  = ParagraphStyle("r_ok", fontSize=9, fontName="Helvetica-Bold",
                          textColor=SUCCESS_GRN)
    err = ParagraphStyle("r_err", fontSize=9, fontName="Helvetica-Bold",
                          textColor=DANGER_RED)

    story = []

    # ── Header block ───────────────────────────────────────────────────────────
    story.append(Paragraph("📅 TimetableCraft", h1))
    story.append(Paragraph(
        f"Generation Report · {term} · {session} · <i>{version}</i>", sub))
    story.append(Paragraph(f"School: <b>{school_name}</b>  ·  Generated: {generated}", body))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_GOLD,
                             spaceAfter=12))

    # ── Status banner ──────────────────────────────────────────────────────────
    status_txt = "✅ ALL CONSTRAINTS SATISFIED" if success \
                 else f"⚠️  {report_data['total_conflicts']} UNRESOLVED CONSTRAINT(S)"
    status_sty = ok if success else err
    story.append(Paragraph(status_txt, status_sty))
    story.append(Spacer(1, 10))

    # ── Summary metrics table ──────────────────────────────────────────────────
    story.append(Paragraph("Summary", h2))
    metrics = [
        ["Metric", "Value"],
        ["Total Periods Assigned", str(report_data.get("total_periods", 0))],
        ["Unresolved Conflicts",   str(report_data.get("total_conflicts", 0))],
        ["Classes Scheduled",      str(report_data.get("classes", 0))],
        ["Subjects Covered",       str(report_data.get("subjects", 0))],
        ["Teachers Active",        str(len(report_data.get("teachers", [])))],
        ["Timetable Version",      version],
        ["Term",                   term],
        ["Academic Session",       session],
    ]
    m_tbl = Table(metrics, colWidths=[9*cm, 7*cm])
    m_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), HEADER_BG),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("ALIGN",      (1,0), (1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, ALT_ROW]),
        ("GRID",       (0,0), (-1,-1), 0.4, colors.HexColor("#CCC")),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
    ]))
    story.append(m_tbl)

    # ── Teacher load table ─────────────────────────────────────────────────────
    story.append(Paragraph("Teacher Workload", h2))
    t_header = [["Teacher", "Type", "Periods Assigned", "Max Cap", "Utilisation"]]
    t_rows   = []
    for t in report_data.get("teachers", []):
        util = f"{t['periods']/max(t['max'],1)*100:.0f}%"
        t_rows.append([
            t["name"], t["staff_type"].title(),
            str(t["periods"]), str(t["max"]), util
        ])
    t_data = t_header + t_rows
    t_tbl  = Table(t_data, colWidths=[6*cm, 3*cm, 3.5*cm, 2.5*cm, 3*cm])
    t_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), HEADER_BG),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("ALIGN",      (2,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, ALT_ROW]),
        ("GRID",       (0,0), (-1,-1), 0.4, colors.HexColor("#CCC")),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
    ]))
    story.append(t_tbl)

    # ── Conflict list ──────────────────────────────────────────────────────────
    conflicts = report_data.get("conflicts", [])
    if conflicts:
        story.append(Paragraph("Unresolved Conflicts", h2))
        c_data = [["Class", "Subject", "Reason"]]
        for c in conflicts:
            c_data.append([
                c.get("class", "—"), c.get("subject", "—"), c.get("reason", "—")
            ])
        c_tbl = Table(c_data, colWidths=[4*cm, 4*cm, 10*cm])
        c_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), DANGER_RED),
            ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1), 8),
            ("ROWBACKGROUNDS", (0,1), (-1,-1),
             [colors.HexColor("#FFF5F5"), colors.HexColor("#FFE9E9")]),
            ("GRID",       (0,0), (-1,-1), 0.4, colors.HexColor("#FFAAAA")),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0),(-1,-1), 5),
            ("WORDWRAP",   (2,0), (2,-1), True),
        ]))
        story.append(c_tbl)
    else:
        story.append(Paragraph("Conflict Report", h2))
        story.append(Paragraph("✅ No conflicts — all scheduling constraints satisfied.", ok))

    doc.build(story,
              onFirstPage=lambda c,d: _page_footer(c,d,"Generation Report",school_name),
              onLaterPages=lambda c,d: _page_footer(c,d,"Generation Report",school_name))
    buf.seek(0)
    print("[pdf] ✅ Generation report PDF ready.")
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# 4. Master CSV
# ══════════════════════════════════════════════════════════════════════════════
def export_master_csv(version=None) -> bytes:
    ver     = version or get_active_version()
    periods = get_all_periods(ver)
    buf     = io.StringIO()
    writer  = csv.DictWriter(buf, fieldnames=[
        "class_name", "arm", "level", "day", "slot_number",
        "start_time", "end_time", "subject_name", "teacher_name",
        "timetable_version"
    ])
    writer.writeheader()
    for p in periods:
        writer.writerow({
            "class_name":         p.get("class_name",""),
            "arm":                p.get("arm",""),
            "level":              p.get("level",""),
            "day":                p.get("day",""),
            "slot_number":        p.get("slot_number",""),
            "start_time":         p.get("start_time",""),
            "end_time":           p.get("end_time",""),
            "subject_name":       p.get("subject_name",""),
            "teacher_name":       p.get("teacher_name",""),
            "timetable_version":  p.get("timetable_version",""),
        })
    print(f"[pdf] ✅ Master CSV: {len(periods)} rows (version={ver})")
    return buf.getvalue().encode("utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# 5. School Statistics Report PDF
# ══════════════════════════════════════════════════════════════════════════════
def export_statistics_report(version=None) -> bytes:
    """
    Comprehensive school statistics PDF:
      - Subject distribution (periods per subject, per class)
      - Teacher utilisation summary
      - Period fill rate by day
    """
    from db import get_subject_distribution, get_teacher_workload_df, get_config, get_active_version
    import pandas as pd

    ver         = version or get_active_version()
    school_name = get_config("school_name", "HMG Academy")
    term        = get_config("current_term", "First Term")
    session     = get_config("current_session", "2024/2025")
    generated   = datetime.now().strftime("%d %B %Y, %H:%M")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2.5*cm, bottomMargin=2*cm,
                            title="School Statistics")

    h1  = ParagraphStyle("s_h1", fontSize=18, fontName="Helvetica-Bold",
                          textColor=BRAND_DARK, spaceAfter=4)
    h2  = ParagraphStyle("s_h2", fontSize=12, fontName="Helvetica-Bold",
                          textColor=BRAND_BLUE, spaceBefore=16, spaceAfter=6)
    sub = ParagraphStyle("s_sub", fontSize=9, fontName="Helvetica",
                          textColor=colors.HexColor("#555"), spaceAfter=12)
    body= ParagraphStyle("s_body", fontSize=9, fontName="Helvetica",
                          textColor=BRAND_DARK, spaceAfter=4)

    story = []
    story.append(Paragraph("📊 School Statistics Report", h1))
    story.append(Paragraph(
        f"{school_name}  ·  {term}  ·  {session}  ·  Version: {ver}  ·  {generated}", sub))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_GOLD, spaceAfter=10))

    # ── Subject Distribution ───────────────────────────────────────────────────
    story.append(Paragraph("Subject Period Distribution", h2))
    dist = get_subject_distribution(ver)
    if dist:
        s_data = [["Subject", "Teacher", "Total Periods", "Classes"]]
        for row in dist:
            s_data.append([
                row["subject_name"],
                row["teacher_name"] or "—",
                str(row["total_periods"]),
                str(row["classes_count"]),
            ])
        s_tbl = Table(s_data, colWidths=[6*cm, 5*cm, 3.5*cm, 3.5*cm])
        s_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), HEADER_BG),
            ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 9),
            ("ALIGN",         (2,0), (-1,-1), "CENTER"),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, ALT_ROW]),
            ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#CCC")),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(s_tbl)
    else:
        story.append(Paragraph("No timetable data for this version.", body))

    # ── Teacher Utilisation ────────────────────────────────────────────────────
    story.append(Paragraph("Teacher Utilisation", h2))
    from db import get_all_teachers as _gat
    from db import count_teacher_periods_per_week as _ctpw
    teachers = _gat()
    if teachers:
        t_data = [["Teacher", "Type", "Periods Assigned", "Max Cap", "Utilisation %"]]
        for t in sorted(teachers, key=lambda x: x["name"]):
            assigned = _ctpw(t["id"], ver)
            cap      = t.get("max_periods_per_week", 30)
            util     = f"{assigned/max(cap,1)*100:.1f}%"
            t_data.append([
                t["name"], t["staff_type"].title(),
                str(assigned), str(cap), util
            ])
        t_tbl = Table(t_data, colWidths=[5.5*cm, 3*cm, 3.5*cm, 2.5*cm, 3.5*cm])
        t_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), HEADER_BG),
            ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 9),
            ("ALIGN",         (2,0), (-1,-1), "CENTER"),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, ALT_ROW]),
            ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#CCC")),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(t_tbl)

    doc.build(story,
              onFirstPage=lambda c,d: _page_footer(c,d,"Statistics Report",school_name),
              onLaterPages=lambda c,d: _page_footer(c,d,"Statistics Report",school_name))
    buf.seek(0)
    print("[pdf] ✅ Statistics report PDF ready.")
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# 6. Compact Single-Page Class Timetable (A4 Portrait — Print-Ready)
# ══════════════════════════════════════════════════════════════════════════════
def export_compact_timetable_pdf(class_id, version=None) -> bytes:
    """
    Print-ready single-page A4 portrait timetable for one class.
    Larger font, bold subject names, suitable for classroom wall display.
    """
    school_name     = get_config("school_name", "HMG Academy")
    term            = get_config("current_term", "First Term")
    session         = get_config("current_session", "2024/2025")
    periods_per_day = int(get_config("periods_per_day", 8))
    ver             = version or get_active_version()

    cls_rec  = get_all_classes()
    cls_data = next((c for c in cls_rec if c["id"] == class_id), None)
    if not cls_data:
        return b""

    class_label = f"{cls_data['name']} {cls_data['arm']}"
    periods     = get_periods_for_class(class_id, ver)
    slot_map    = {(p["day"], p["slot_number"]): p for p in periods}
    present_days = [d for d in DAY_ORDER if any(p["day"] == d for p in periods)] or DAY_ORDER[:5]

    specials    = get_all_special_slots()
    special_map = {int(s["position"]): s for s in specials}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=1.5*cm,
                            title=f"{class_label} Timetable")

    title_sty = ParagraphStyle("ct_t", fontSize=16, fontName="Helvetica-Bold",
                                textColor=BRAND_DARK, alignment=TA_CENTER, spaceAfter=2)
    sub_sty   = ParagraphStyle("ct_s", fontSize=9, fontName="Helvetica",
                                textColor=colors.HexColor("#555"), alignment=TA_CENTER,
                                spaceAfter=10)
    cell_sty  = ParagraphStyle("ct_c", fontSize=8, fontName="Helvetica-Bold",
                                alignment=TA_CENTER, leading=11)
    sm_sty    = ParagraphStyle("ct_sm", fontSize=6.5, fontName="Helvetica",
                                alignment=TA_CENTER, leading=8)

    story = []
    story.append(Paragraph(school_name, title_sty))
    story.append(Paragraph(
        f"Class Timetable — {class_label} ({cls_data['level']})  ·  "
        f"{term}  ·  {session}  ·  {ver}", sub_sty))

    # Build rows with special slots
    header    = ["Period"] + present_days
    data_rows = [header]
    style_cmds = []
    color_map  = {}
    row_cursor = 0

    if 0 in special_map:
        sp = special_map[0]
        sp_row = [Paragraph(f"<b>{sp['label']}</b>", sm_sty)]
        for day in present_days:
            sp_row.append(Paragraph(
                f"<b>{sp['label']}</b><br/><font size='5'>{sp['duration']}min</font>",
                sm_sty) if day in sp["days"].split(",") else Paragraph("", sm_sty))
        data_rows.append(sp_row)
        ri = row_cursor + 1
        style_cmds += [
            ("BACKGROUND", (0,ri),(-1,ri), hex_to_rl(sp["color_hex"])),
            ("TEXTCOLOR",  (0,ri),(-1,ri), colors.white),
        ]
        row_cursor += 1

    for slot in range(1, periods_per_day + 1):
        row = [Paragraph(f"<b>{_ordinal(slot)}</b>", cell_sty)]
        for ci, day in enumerate(present_days, start=1):
            rec = slot_map.get((day, slot))
            ri  = row_cursor + 1
            if rec and rec.get("subject_name"):
                row.append(Paragraph(
                    f"<b>{rec['subject_name']}</b><br/>"
                    f"<font size='6'>{rec.get('teacher_name','')}</font><br/>"
                    f"<font size='5'>{rec['start_time']}–{rec['end_time']}</font>",
                    cell_sty))
                color_map[(ri, ci)] = rec.get("color_hex", "#4A90D9")
            else:
                row.append(Paragraph("—", sm_sty))
        data_rows.append(row)
        row_cursor += 1

        if slot in special_map:
            sp = special_map[slot]
            sp_row = [Paragraph(f"<b>{sp['label']}</b>", sm_sty)]
            for day in present_days:
                sp_row.append(Paragraph(
                    f"<b>{sp['label']}</b><br/><font size='5'>{sp['duration']}min</font>",
                    sm_sty) if day in sp["days"].split(",") else Paragraph("", sm_sty))
            data_rows.append(sp_row)
            ri = row_cursor + 1
            style_cmds += [
                ("BACKGROUND", (0,ri),(-1,ri), hex_to_rl(sp["color_hex"])),
                ("TEXTCOLOR",  (0,ri),(-1,ri), colors.white),
            ]
            row_cursor += 1

    pw        = A4[0] - 3*cm
    day_w     = (pw - 2*cm) / len(present_days)
    col_widths= [2*cm] + [day_w]*len(present_days)

    tbl = Table(data_rows, colWidths=col_widths,
                rowHeights=[None]*len(data_rows))
    ts  = TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), HEADER_BG),
        ("TEXTCOLOR",     (0,0),(-1,0), colors.white),
        ("FONTNAME",      (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,0), 9),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, ALT_ROW]),
        ("GRID",          (0,0),(-1,-1), 0.5, colors.HexColor("#CCC")),
        ("LINEBELOW",     (0,0),(-1,0), 2, BRAND_GOLD),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
    ])
    for cmd in style_cmds:
        ts.add(*cmd)
    for (ri, ci), hex_c in color_map.items():
        ts.add("BACKGROUND", (ci,ri),(ci,ri), hex_to_rl(hex_c))
        ts.add("TEXTCOLOR",  (ci,ri),(ci,ri), colors.white)
    tbl.setStyle(ts)
    story.append(tbl)

    doc.build(story,
              onFirstPage=lambda c,d: _page_footer(c,d,f"{class_label} Timetable",school_name),
              onLaterPages=lambda c,d: _page_footer(c,d,f"{class_label} Timetable",school_name))
    buf.seek(0)
    print(f"[pdf] ✅ Compact timetable: {class_label}")
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# 7. Exam Timetable PDF
# ══════════════════════════════════════════════════════════════════════════════
def export_exam_timetable_pdf(exam_slots, school_name="", term="", session="") -> bytes:
    """
    Generates an A4 landscape exam timetable PDF from a list of exam_slot dicts.
    Groups rows by exam_date for a clean day-by-day layout.
    """
    from collections import defaultdict
    school_name = school_name or get_config("school_name", "HMG Academy")
    term        = term        or get_config("current_term", "First Term")
    session     = session     or get_config("current_session", "2024/2025")
    generated   = datetime.now().strftime("%d %B %Y, %H:%M")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm,
                            title="Exam Timetable")

    h1   = ParagraphStyle("ex_h1", fontSize=16, fontName="Helvetica-Bold",
                           textColor=BRAND_DARK, alignment=TA_CENTER, spaceAfter=4)
    sub  = ParagraphStyle("ex_sub", fontSize=9, fontName="Helvetica",
                           textColor=colors.HexColor("#555"), alignment=TA_CENTER,
                           spaceAfter=12)
    h2   = ParagraphStyle("ex_h2", fontSize=11, fontName="Helvetica-Bold",
                           textColor=BRAND_BLUE, spaceBefore=10, spaceAfter=4)
    cell = ParagraphStyle("ex_cell", fontSize=8, fontName="Helvetica-Bold",
                           alignment=TA_CENTER, leading=10)
    sm   = ParagraphStyle("ex_sm", fontSize=7, fontName="Helvetica",
                           alignment=TA_CENTER, leading=9)

    story = []
    story.append(Paragraph(school_name, h1))
    story.append(Paragraph(
        f"Examination Timetable  ·  {term}  ·  {session}  ·  Generated: {generated}", sub))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_GOLD, spaceAfter=8))

    if not exam_slots:
        story.append(Paragraph("No exam slots have been scheduled yet.", sm))
    else:
        # Group by date
        by_date = defaultdict(list)
        for e in exam_slots:
            by_date[e["exam_date"]].append(e)

        for exam_date in sorted(by_date.keys()):
            slots = sorted(by_date[exam_date], key=lambda x: x["start_time"])
            story.append(Paragraph(
                f"📅  {_format_date(exam_date)}", h2))

            header = ["Time", "Subject", "Class", "Venue", "Invigilator", "Notes"]
            rows   = [header]
            for s in slots:
                rows.append([
                    Paragraph(f"{s['start_time']}–{s['end_time']}", cell),
                    Paragraph(f"<b>{s.get('subject_name','—')}</b>", cell),
                    Paragraph(f"{s.get('class_name','')} {s.get('arm','')}".strip(), cell),
                    Paragraph(s.get("venue","—") or "—", sm),
                    Paragraph(s.get("invigilator_name","—") or "—", sm),
                    Paragraph(s.get("notes","") or "", sm),
                ])

            col_w = [3*cm, 5*cm, 3*cm, 3.5*cm, 4.5*cm, 5*cm]
            tbl   = Table(rows, colWidths=col_w)
            ts    = TableStyle([
                ("BACKGROUND",    (0,0),(-1,0), HEADER_BG),
                ("TEXTCOLOR",     (0,0),(-1,0), colors.white),
                ("FONTNAME",      (0,0),(-1,0), "Helvetica-Bold"),
                ("FONTSIZE",      (0,0),(-1,0), 9),
                ("ALIGN",         (0,0),(-1,-1), "CENTER"),
                ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, ALT_ROW]),
                ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#CCC")),
                ("TOPPADDING",    (0,0),(-1,-1), 5),
                ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ])
            tbl.setStyle(ts)
            story.append(tbl)
            story.append(Spacer(1, 8))

    doc.build(story,
              onFirstPage=lambda c,d: _page_footer(c,d,"Exam Timetable",school_name),
              onLaterPages=lambda c,d: _page_footer(c,d,"Exam Timetable",school_name))
    buf.seek(0)
    print("[pdf] ✅ Exam timetable PDF ready.")
    return buf.read()


def _format_date(date_str):
    """Convert YYYY-MM-DD to a readable format like 'Monday, 10 June 2024'."""
    try:
        from datetime import datetime as _dt
        d = _dt.strptime(date_str, "%Y-%m-%d")
        return d.strftime("%A, %d %B %Y")
    except Exception:
        return date_str


# ══════════════════════════════════════════════════════════════════════════════
# 8. Student Register PDF (class list)
# ══════════════════════════════════════════════════════════════════════════════
def export_student_register_pdf(class_id, students) -> bytes:
    """
    Generates an A4 portrait student register (class list) for one class.
    Includes roll number, name, gender, and signature columns.
    """
    school_name = get_config("school_name", "HMG Academy")
    term        = get_config("current_term", "First Term")
    session     = get_config("current_session", "2024/2025")

    cls_list  = get_all_classes()
    cls_data  = next((c for c in cls_list if c["id"] == class_id), {})
    cls_label = f"{cls_data.get('name','')} {cls_data.get('arm','')}".strip()
    generated = datetime.now().strftime("%d %B %Y")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm,
                            title=f"{cls_label} Register")

    h1   = ParagraphStyle("reg_h1", fontSize=16, fontName="Helvetica-Bold",
                           textColor=BRAND_DARK, alignment=TA_CENTER, spaceAfter=3)
    sub  = ParagraphStyle("reg_sub", fontSize=9, fontName="Helvetica",
                           textColor=colors.HexColor("#555"), alignment=TA_CENTER,
                           spaceAfter=12)
    cell = ParagraphStyle("reg_c", fontSize=9, fontName="Helvetica",
                           alignment=TA_LEFT, leading=11)
    ctr  = ParagraphStyle("reg_ctr", fontSize=9, fontName="Helvetica",
                           alignment=TA_CENTER, leading=11)

    story = []
    story.append(Paragraph(school_name, h1))
    story.append(Paragraph(
        f"Student Register — {cls_label}  ·  {term}  ·  {session}  ·  {generated}", sub))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_GOLD, spaceAfter=10))

    m_count = sum(1 for s in students if s.get("gender") == "M")
    f_count = sum(1 for s in students if s.get("gender") == "F")
    story.append(Paragraph(
        f"Total Students: <b>{len(students)}</b>   |   Male: <b>{m_count}</b>   "
        f"|   Female: <b>{f_count}</b>",
        ParagraphStyle("reg_stat", fontSize=9, fontName="Helvetica",
                       textColor=BRAND_DARK, spaceAfter=10)))

    header = [["#", "Roll No.", "Last Name", "First Name", "Gender", "Signature"]]
    rows   = []
    for i, s in enumerate(students, 1):
        rows.append([
            Paragraph(str(i), ctr),
            Paragraph(s.get("roll_number",""), ctr),
            Paragraph(s.get("last_name",""), cell),
            Paragraph(s.get("first_name",""), cell),
            Paragraph(s.get("gender",""), ctr),
            Paragraph("", cell),
        ])

    table_data = header + rows
    col_w = [1*cm, 2.5*cm, 4*cm, 4*cm, 2*cm, 4*cm]
    tbl   = Table(table_data, colWidths=col_w,
                  repeatRows=1)
    ts    = TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), HEADER_BG),
        ("TEXTCOLOR",     (0,0),(-1,0), colors.white),
        ("FONTNAME",      (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("ALIGN",         (2,1),(3,-1), "LEFT"),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, ALT_ROW]),
        ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#CCC")),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LINEBELOW",     (0,0),(-1,0), 2, BRAND_GOLD),
    ])
    tbl.setStyle(ts)
    story.append(tbl)

    doc.build(story,
              onFirstPage=lambda c,d: _page_footer(c,d,"Student Register",school_name),
              onLaterPages=lambda c,d: _page_footer(c,d,"Student Register",school_name))
    buf.seek(0)
    print(f"[pdf] ✅ Student register PDF: {cls_label} ({len(students)} students)")
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# 9. Teacher Report Card PDF
# ══════════════════════════════════════════════════════════════════════════════
def export_teacher_report_pdf(teacher, periods, version=None) -> bytes:
    """
    One-page PDF report card for a single teacher:
    - Personal details, staff type, available days
    - Subjects taught, classes covered
    - Total periods, free periods, utilisation
    - Day-by-day period breakdown table
    """
    school_name = get_config("school_name", "HMG Academy")
    term        = get_config("current_term", "First Term")
    session     = get_config("current_session", "2024/2025")
    ver         = version or get_active_version()
    ppd         = int(get_config("periods_per_day", 8))
    n_days      = len(get_config("school_days",
                      "Monday,Tuesday,Wednesday,Thursday,Friday").split(","))
    total_slots = n_days * ppd
    total_p     = len(periods)
    free_p      = total_slots - total_p
    cap         = teacher.get("max_periods_per_week", 30)
    util        = f"{total_p / max(cap,1) * 100:.1f}%"
    generated   = datetime.now().strftime("%d %B %Y, %H:%M")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm,
                            title=f"{teacher['name']} Report")

    h1   = ParagraphStyle("tr_h1", fontSize=16, fontName="Helvetica-Bold",
                           textColor=BRAND_DARK, alignment=TA_CENTER, spaceAfter=3)
    sub  = ParagraphStyle("tr_sub", fontSize=9, fontName="Helvetica",
                           textColor=colors.HexColor("#555"), alignment=TA_CENTER,
                           spaceAfter=10)
    h2   = ParagraphStyle("tr_h2", fontSize=11, fontName="Helvetica-Bold",
                           textColor=BRAND_BLUE, spaceBefore=12, spaceAfter=6)
    body = ParagraphStyle("tr_body", fontSize=9, fontName="Helvetica",
                           textColor=BRAND_DARK, spaceAfter=4)
    cell = ParagraphStyle("tr_cell", fontSize=8, fontName="Helvetica",
                           alignment=TA_CENTER, leading=10)

    story = []
    story.append(Paragraph(school_name, h1))
    story.append(Paragraph(
        f"Teacher Report Card  ·  {teacher['name']}  ·  {term}  ·  {session}  ·  {ver}",
        sub))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_GOLD, spaceAfter=10))

    # Summary metrics table
    story.append(Paragraph("Summary", h2))
    summary_data = [
        ["Staff Type",       teacher["staff_type"].title()],
        ["Available Days",   teacher.get("available_days","—")],
        ["Max Periods/Week", str(cap)],
        ["Periods Assigned", str(total_p)],
        ["Free Periods",     str(free_p)],
        ["Utilisation",      util],
        ["Version",          ver],
    ]
    s_tbl = Table(summary_data, colWidths=[6*cm, 11*cm])
    s_tbl.setStyle(TableStyle([
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("FONTNAME",      (0,0),(0,-1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [colors.white, ALT_ROW]),
        ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#CCC")),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
    ]))
    story.append(s_tbl)

    # Distinct classes and subjects
    classes_taught  = sorted({f"{p['class_name']} {p['arm']}" for p in periods})
    subjects_taught = sorted({p["subject_name"] for p in periods})
    story.append(Paragraph("Classes Taught", h2))
    story.append(Paragraph(", ".join(classes_taught) if classes_taught else "None", body))
    story.append(Paragraph("Subjects Taught", h2))
    story.append(Paragraph(", ".join(subjects_taught) if subjects_taught else "None", body))

    # Day-by-day breakdown
    if periods:
        story.append(Paragraph("Period Schedule", h2))
        slot_map = {(p["day"], p["slot_number"]): p for p in periods}
        days_present = [d for d in DAY_ORDER
                        if any(p["day"] == d for p in periods)]
        header = ["Slot"] + days_present
        sched_rows = [header]
        ppd_val = int(get_config("periods_per_day", 8))
        for slot in range(1, ppd_val + 1):
            row = [Paragraph(str(slot), cell)]
            for day in days_present:
                rec = slot_map.get((day, slot))
                if rec:
                    row.append(Paragraph(
                        f"{rec['subject_name']}\n{rec['class_name']} {rec['arm']}", cell))
                else:
                    row.append(Paragraph("—", cell))
            sched_rows.append(row)
        day_w  = (A4[0] - 4*cm - 1.5*cm) / len(days_present)
        col_ws = [1.5*cm] + [day_w] * len(days_present)
        sch_tbl = Table(sched_rows, colWidths=col_ws)
        sch_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0), HEADER_BG),
            ("TEXTCOLOR",     (0,0),(-1,0), colors.white),
            ("FONTNAME",      (0,0),(-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1,-1), 8),
            ("ALIGN",         (0,0),(-1,-1), "CENTER"),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, ALT_ROW]),
            ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#CCC")),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ]))
        story.append(sch_tbl)

    doc.build(story,
              onFirstPage=lambda c,d: _page_footer(c,d,"Teacher Report",school_name),
              onLaterPages=lambda c,d: _page_footer(c,d,"Teacher Report",school_name))
    buf.seek(0)
    print(f"[pdf] ✅ Teacher report: {teacher['name']}")
    return buf.read()
