"""
================================================================================
TimetableCraft — scheduler.py  (v2)
Constraint Satisfaction Engine with Greedy Initialisation & LP Conflict Resolution
HMG Concepts | AI-Augmented Solutions
================================================================================
v2 Changes:
  - Version-aware: generates into a named timetable_version tag
  - Class–subject aware: only schedules subjects mapped to each class
    via class_subjects table; falls back to all subjects if no mapping exists
  - Special slots (Assembly, Break) shift real period start times correctly
  - generate_report(): structured post-generation PDF summary data
================================================================================
"""

import json
import random
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Tuple, Optional
import pandas as pd

from db import (
    get_all_teachers, get_all_subjects, get_all_classes,
    get_subjects_for_class, get_subject_ids_for_class,
    get_all_special_slots,
    insert_period, clear_periods,
    get_config, get_all_config, get_active_version,
    get_all_periods
)

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


# ══════════════════════════════════════════════════════════════════════════════
# Time Utilities
# ══════════════════════════════════════════════════════════════════════════════
def build_slot_times(config: dict) -> Dict[str, List[Tuple[str, str]]]:
    """
    Returns {day: [(start, end), ...]} for every teaching slot.
    Assembly time (if > 0) is consumed before slot 1.
    Special slots shift the clock forward at their configured positions.
    """
    periods_per_day  = int(config.get("periods_per_day", 8))
    mon_thu_dur      = int(config.get("mon_thu_duration", 40))
    fri_dur          = int(config.get("fri_duration", 30))
    day_start        = config.get("day_start_time", "08:00").strip()
    assembly_dur     = int(config.get("assembly_duration", 15))
    school_days      = config.get("school_days",
                        "Monday,Tuesday,Wednesday,Thursday,Friday").split(",")

    # Build a position→duration map from special_slots
    # position 0 = before slot 1, position N = after slot N
    special = get_all_special_slots()
    gap_map: Dict[int, int] = {}
    for s in special:
        pos = int(s["position"])
        dur = int(s["duration"])
        gap_map[pos] = gap_map.get(pos, 0) + dur

    # Assembly counts as position-0 gap
    if assembly_dur > 0:
        gap_map[0] = gap_map.get(0, 0)   # assembly already in special_slots seed

    slot_times: Dict[str, List[Tuple[str, str]]] = {}
    for day in school_days:
        duration = fri_dur if day == "Friday" else mon_thu_dur
        slots: List[Tuple[str, str]] = []
        current = datetime.strptime(day_start, "%H:%M")

        # Gap before slot 1 (Assembly etc.)
        if 0 in gap_map:
            current += timedelta(minutes=gap_map[0])

        for slot_idx in range(1, periods_per_day + 1):
            start = current.strftime("%H:%M")
            current += timedelta(minutes=duration)
            end = current.strftime("%H:%M")
            slots.append((start, end))

            # Gap after this slot (Break, Lunch etc.)
            if slot_idx in gap_map:
                current += timedelta(minutes=gap_map[slot_idx])

        slot_times[day] = slots

    return slot_times


# ══════════════════════════════════════════════════════════════════════════════
# Conflict Registry
# ══════════════════════════════════════════════════════════════════════════════
class ConflictRegistry:
    def __init__(self):
        self._occupied: Dict[int, set] = defaultdict(set)
        self._class_slots: Dict[int, Dict[str, set]] = defaultdict(
            lambda: defaultdict(set))
        self._subject_counts: Dict[Tuple[int, int], int] = defaultdict(int)

    def is_teacher_free(self, teacher_id, day, slot):
        return (day, slot) not in self._occupied[teacher_id]

    def is_class_slot_free(self, class_id, day, slot):
        return slot not in self._class_slots[class_id][day]

    def assign(self, teacher_id, class_id, subject_id, day, slot):
        self._occupied[teacher_id].add((day, slot))
        self._class_slots[class_id][day].add(slot)
        self._subject_counts[(class_id, subject_id)] += 1

    def subject_count(self, class_id, subject_id):
        return self._subject_counts[(class_id, subject_id)]

    def teacher_total_periods(self, teacher_id):
        return len(self._occupied[teacher_id])


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1: Greedy Constraint-First Assignment
# ══════════════════════════════════════════════════════════════════════════════
def greedy_assign(classes, subjects, teachers, slot_times,
                  config, registry, assigned_records, conflicts):
    school_days      = config.get("school_days",
                        "Monday,Tuesday,Wednesday,Thursday,Friday").split(",")
    periods_per_day  = int(config.get("periods_per_day", 8))
    double_enabled   = config.get("double_periods_enabled", "true").lower() == "true"
    teacher_map      = {t["id"]: t for t in teachers}

    # All subjects indexed for fast lookup
    all_subjects_map = {s["id"]: s for s in subjects}

    def scarcity(subj):
        return 0 if subj.get("assigned_teacher_id") else 1

    for cls in classes:
        class_id    = cls["id"]
        class_label = f"{cls['name']} {cls['arm']}"

        # ── Use class-specific subject mapping if it exists ───────────────────
        mapped_ids = get_subject_ids_for_class(class_id)
        if mapped_ids:
            class_subjects = [all_subjects_map[sid]
                              for sid in mapped_ids if sid in all_subjects_map]
        else:
            class_subjects = subjects   # fallback: all subjects

        class_subjects_sorted = sorted(class_subjects, key=scarcity)

        day_rotation = school_days.copy()
        random.shuffle(day_rotation)

        for subj in class_subjects_sorted:
            subject_id           = subj["id"]
            subject_name         = subj["name"]
            periods_needed       = int(subj["periods_per_week"])
            assigned_teacher_id  = subj.get("assigned_teacher_id")
            allow_double         = bool(subj.get("allow_double", 0)) and double_enabled

            if not assigned_teacher_id:
                conflicts.append({
                    "class": class_label, "subject": subject_name,
                    "reason": "No teacher assigned to this subject",
                })
                continue

            teacher = teacher_map.get(assigned_teacher_id)
            if not teacher:
                conflicts.append({
                    "class": class_label, "subject": subject_name,
                    "reason": f"Teacher ID={assigned_teacher_id} not found",
                })
                continue

            teacher_available_days = set(teacher["available_days"].split(","))
            max_periods            = int(teacher.get("max_periods_per_week", 30))
            periods_assigned       = 0
            doubled_this_subject   = False

            for day in day_rotation:
                if periods_assigned >= periods_needed:
                    break
                if teacher["staff_type"] == "parttime" and day not in teacher_available_days:
                    continue

                for slot_idx in range(1, periods_per_day + 1):
                    if periods_assigned >= periods_needed:
                        break
                    if not registry.is_teacher_free(assigned_teacher_id, day, slot_idx):
                        continue
                    if not registry.is_class_slot_free(class_id, day, slot_idx):
                        continue
                    if registry.teacher_total_periods(assigned_teacher_id) >= max_periods:
                        conflicts.append({
                            "class": class_label, "subject": subject_name,
                            "reason": f"Teacher '{teacher['name']}' at max weekly load",
                        })
                        periods_assigned = periods_needed
                        break

                    start_t, end_t = slot_times[day][slot_idx - 1]

                    use_double = False
                    if (allow_double and not doubled_this_subject
                            and periods_assigned < periods_needed - 1
                            and slot_idx < periods_per_day):
                        next_slot = slot_idx + 1
                        if (registry.is_teacher_free(assigned_teacher_id, day, next_slot)
                                and registry.is_class_slot_free(class_id, day, next_slot)):
                            use_double = True

                    registry.assign(assigned_teacher_id, class_id, subject_id, day, slot_idx)
                    assigned_records.append({
                        "day": day, "slot_number": slot_idx,
                        "start_time": start_t, "end_time": end_t,
                        "class_id": class_id, "subject_id": subject_id,
                        "teacher_id": assigned_teacher_id, "is_double": use_double,
                    })
                    periods_assigned += 1

                    if use_double:
                        ns = slot_idx + 1
                        s2s, s2e = slot_times[day][ns - 1]
                        registry.assign(assigned_teacher_id, class_id, subject_id, day, ns)
                        assigned_records.append({
                            "day": day, "slot_number": ns,
                            "start_time": s2s, "end_time": s2e,
                            "class_id": class_id, "subject_id": subject_id,
                            "teacher_id": assigned_teacher_id, "is_double": True,
                        })
                        periods_assigned += 1
                        doubled_this_subject = True

            if periods_assigned < periods_needed:
                conflicts.append({
                    "class": class_label, "subject": subject_name,
                    "reason": (
                        f"Only {periods_assigned}/{periods_needed} periods scheduled "
                        f"(teacher conflicts or insufficient free slots)"
                    ),
                })


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2: PuLP LP Conflict Resolution
# ══════════════════════════════════════════════════════════════════════════════
def lp_resolve(unresolved, classes, subjects, teachers,
               slot_times, config, registry, assigned_records):
    try:
        import pulp
    except ImportError:
        print("[scheduler] ⚠️  PuLP not installed — skipping LP phase.")
        return unresolved

    school_days     = config.get("school_days",
                       "Monday,Tuesday,Wednesday,Thursday,Friday").split(",")
    periods_per_day = int(config.get("periods_per_day", 8))
    teacher_map     = {t["id"]: t for t in teachers}
    class_map       = {c["id"]: c for c in classes}
    subject_map     = {s["id"]: s for s in subjects}

    unresolved_pairs = {}
    for item in unresolved:
        for cls in classes:
            if item["class"] == f"{cls['name']} {cls['arm']}":
                for subj in subjects:
                    if subj["name"] == item["subject"]:
                        key = (cls["id"], subj["id"])
                        assigned = registry.subject_count(cls["id"], subj["id"])
                        still_needed = int(subj["periods_per_week"]) - assigned
                        if still_needed > 0:
                            unresolved_pairs[key] = still_needed

    if not unresolved_pairs:
        return []

    still_unresolved = []
    print(f"[scheduler] 🔄 LP Phase 2: {len(unresolved_pairs)} pairs")

    for (class_id, subject_id), needed in unresolved_pairs.items():
        subj    = subject_map.get(subject_id)
        cls     = class_map.get(class_id)
        if not subj or not cls:
            continue
        tid     = subj.get("assigned_teacher_id")
        if not tid:
            continue
        teacher = teacher_map.get(tid)
        if not teacher:
            continue

        teacher_days = set(teacher["available_days"].split(","))
        max_p        = int(teacher.get("max_periods_per_week", 30))

        feasible = [
            (day, slot)
            for day in school_days
            if not (teacher["staff_type"] == "parttime" and day not in teacher_days)
            for slot in range(1, periods_per_day + 1)
            if (registry.is_teacher_free(tid, day, slot)
                and registry.is_class_slot_free(class_id, day, slot)
                and registry.teacher_total_periods(tid) < max_p)
        ]

        if not feasible:
            still_unresolved.append({
                "class": f"{cls['name']} {cls['arm']}",
                "subject": subj["name"],
                "reason": "LP Phase: no feasible slots after full constraint evaluation",
            })
            continue

        prob = pulp.LpProblem(f"lp_{class_id}_{subject_id}", pulp.LpMaximize)
        x    = {(d, s): pulp.LpVariable(f"x_{d}_{s}", cat="Binary") for d, s in feasible}
        prob += pulp.lpSum(x.values())
        prob += pulp.lpSum(x.values()) <= needed
        for day in school_days:
            dv = [x[(d, s)] for (d, s) in feasible if d == day]
            if dv:
                prob += pulp.lpSum(dv) <= 1
        prob.solve(pulp.PULP_CBC_CMD(msg=0))

        assigned_here = 0
        for (day, slot), var in x.items():
            if pulp.value(var) and pulp.value(var) > 0.5:
                start_t, end_t = slot_times[day][slot - 1]
                registry.assign(tid, class_id, subject_id, day, slot)
                assigned_records.append({
                    "day": day, "slot_number": slot,
                    "start_time": start_t, "end_time": end_t,
                    "class_id": class_id, "subject_id": subject_id,
                    "teacher_id": tid, "is_double": False,
                })
                assigned_here += 1

        if assigned_here < needed:
            still_unresolved.append({
                "class": f"{cls['name']} {cls['arm']}",
                "subject": subj["name"],
                "reason": f"LP: assigned {assigned_here}/{needed} — residual conflict",
            })
        else:
            print(f"[scheduler] ✅ LP resolved: {cls['name']} {cls['arm']} — {subj['name']}")

    return still_unresolved


# ══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ══════════════════════════════════════════════════════════════════════════════
def generate_timetable(seed: int = 42, version: str = None) -> dict:
    """
    Full two-phase timetable generation pipeline.
    Generates into the specified version tag (defaults to active version).
    """
    random.seed(seed)
    ver = version or get_active_version()

    print(f"\n[scheduler] ═══ TimetableCraft — Generating [{ver}] ═══")
    print("[scheduler] Constraint Satisfaction + LP Conflict Resolution")

    config   = get_all_config()
    teachers = get_all_teachers()
    subjects = get_all_subjects()
    classes  = get_all_classes()

    for label, items in [("classes", classes), ("subjects", subjects), ("teachers", teachers)]:
        if not items:
            return {"success": False, "periods_assigned": 0,
                    "conflicts": [{"reason": f"No {label} defined"}], "stats": {}}

    slot_times       = build_slot_times(config)
    registry         = ConflictRegistry()
    assigned_records = []
    conflicts        = []

    print(f"[scheduler] Phase 1 → Greedy ({len(classes)} classes × {len(subjects)} subjects)")
    greedy_assign(classes, subjects, teachers, slot_times,
                  config, registry, assigned_records, conflicts)
    print(f"[scheduler] Phase 1 done: {len(assigned_records)} assigned, "
          f"{len(conflicts)} conflicts")

    if conflicts:
        print(f"[scheduler] Phase 2 → LP resolution ({len(conflicts)} items)")
        final_conflicts = lp_resolve(
            conflicts, classes, subjects, teachers,
            slot_times, config, registry, assigned_records
        )
    else:
        final_conflicts = []

    # Persist
    clear_periods(version=ver)
    for rec in assigned_records:
        insert_period(**rec, version=ver)

    teacher_loads = {
        t["name"]: registry.teacher_total_periods(t["id"])
        for t in teachers
    }

    stats = {
        "total_periods":     len(assigned_records),
        "total_conflicts":   len(final_conflicts),
        "teacher_loads":     teacher_loads,
        "classes_scheduled": len(classes),
        "subjects_covered":  len([s for s in subjects if s.get("assigned_teacher_id")]),
        "version":           ver,
        "term":              config.get("current_term", "First Term"),
        "session":           config.get("current_session", "2024/2025"),
        "school_name":       config.get("school_name", "HMG Academy"),
    }

    print(f"\n[scheduler] ✅ Done! {stats['total_periods']} periods | "
          f"{stats['total_conflicts']} unresolved | version={ver}")

    return {
        "success":          len(final_conflicts) == 0,
        "periods_assigned": stats["total_periods"],
        "conflicts":        final_conflicts,
        "stats":            stats,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Analytics Helpers
# ══════════════════════════════════════════════════════════════════════════════
def get_teacher_workload_df(version=None) -> pd.DataFrame:
    periods = get_all_periods(version)
    if not periods:
        return pd.DataFrame(columns=["teacher", "periods"])
    df = pd.DataFrame(periods)
    return (df.groupby("teacher_name")["id"].count()
              .reset_index()
              .rename(columns={"teacher_name": "teacher", "id": "periods"})
              .sort_values("periods", ascending=False))


def get_utilisation_heatmap_df(version=None) -> pd.DataFrame:
    periods = get_all_periods(version)
    classes = get_all_classes()
    if not periods or not classes:
        return pd.DataFrame()
    df       = pd.DataFrame(periods)
    n_cls    = len(classes)
    pivot    = df.pivot_table(index="slot_number", columns="day",
                               values="id", aggfunc="count", fill_value=0)
    pivot    = pivot / n_cls
    present  = [d for d in DAY_ORDER if d in pivot.columns]
    return pivot[present]


def get_free_period_df(version=None) -> pd.DataFrame:
    teachers  = get_all_teachers()
    periods   = get_all_periods(version)
    n_days    = len(get_config("school_days",
                    "Monday,Tuesday,Wednesday,Thursday,Friday").split(","))
    ppd       = int(get_config("periods_per_day", 8))
    total     = n_days * ppd
    if not periods:
        return pd.DataFrame({
            "teacher":      [t["name"] for t in teachers],
            "free_periods": [total] * len(teachers)
        })
    df       = pd.DataFrame(periods)
    assigned = df.groupby("teacher_name")["id"].count().to_dict()
    rows     = [{"teacher": t["name"],
                 "free_periods": max(0, total - assigned.get(t["name"], 0))}
                for t in teachers]
    return pd.DataFrame(rows).sort_values("free_periods", ascending=False)


# ══════════════════════════════════════════════════════════════════════════════
# Post-Generation Report Data
# ══════════════════════════════════════════════════════════════════════════════
def build_report_data(result: dict) -> dict:
    """
    Assemble all data needed to render the post-generation PDF report.
    Returns a structured dict consumed by pdf_gen.export_generation_report().
    """
    stats    = result.get("stats", {})
    teachers = get_all_teachers()
    loads    = stats.get("teacher_loads", {})

    teacher_rows = []
    for t in teachers:
        teacher_rows.append({
            "name":       t["name"],
            "staff_type": t["staff_type"],
            "periods":    loads.get(t["name"], 0),
            "max":        t.get("max_periods_per_week", 30),
        })
    teacher_rows.sort(key=lambda r: r["periods"], reverse=True)

    return {
        "school_name":    stats.get("school_name", "HMG Academy"),
        "term":           stats.get("term", "First Term"),
        "session":        stats.get("session", "2024/2025"),
        "version":        stats.get("version", "v1"),
        "total_periods":  stats.get("total_periods", 0),
        "total_conflicts":stats.get("total_conflicts", 0),
        "classes":        stats.get("classes_scheduled", 0),
        "subjects":       stats.get("subjects_covered", 0),
        "teachers":       teacher_rows,
        "conflicts":      result.get("conflicts", []),
        "success":        result.get("success", False),
    }
