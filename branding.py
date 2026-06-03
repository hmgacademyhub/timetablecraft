"""
================================================================================
TimetableCraft — branding.py
HMG Concepts | HMG Technologies — AI-Augmented Solutions
================================================================================
Central source-of-truth for every brand string, link, colour, and
attribution used anywhere in the app. Change it here, change it everywhere.

Brand owner    : HMG Concepts  (His Marvellous Grace Educational Consult)
Subsidiary     : HMG Technologies — the EdTech / Data arm
Built for      : HMG Academy and partner Nigerian schools
Built by       : Adewale Samson Adeagbo
Role           : AI-Augmented Solutions Developer · Data Scientist · Educator
Founded        : 2015 · Lagos, Nigeria
Philosophy     : "Learning Deliberately. Teaching Authentically."
================================================================================
"""

# ── Product ───────────────────────────────────────────────────────────────────
PRODUCT_NAME      = "TimetableCraft"
PRODUCT_TAGLINE   = "Constraint-Aware Timetable Scheduling for African Schools"
PRODUCT_VERSION   = "v5.2.3"
PRODUCT_EMOJI     = "📅"

# ── Vendor / Brand ────────────────────────────────────────────────────────────
VENDOR            = "HMG Technologies"
PARENT_BRAND      = "HMG Concepts"
PARENT_FULL_NAME  = "His Marvellous Grace Educational Consult"
PARENT_TAGLINE    = "Learning Deliberately. Teaching Authentically."
ACADEMY           = "HMG Academy"
FOUNDED_YEAR      = 2015
LOCATION          = "Lagos, Nigeria"

# ── Founder ───────────────────────────────────────────────────────────────────
FOUNDER_NAME      = "Adewale Samson Adeagbo"
FOUNDER_TITLE     = "AI-Augmented Solutions Developer · Data Scientist · Educator"
FOUNDER_BIO_SHORT = (
    "15+ years in Nigerian classrooms · 12 deployed ML & EdTech projects · "
    "Founder of HMG Concepts."
)

# ── Links ─────────────────────────────────────────────────────────────────────
URL_CONCEPTS      = "https://hmgconcepts.pages.dev"
URL_ACADEMY       = "https://hmgacademy.pages.dev"
URL_FOUNDER       = "https://cssadewale.pages.dev"
URL_GITHUB        = "https://github.com/cssadewale"
URL_LINKEDIN      = "https://linkedin.com/in/adewalesamsonadeagbo"
URL_YOUTUBE       = "https://youtube.com/@hmgconcepts"
URL_WHATSAPP      = "https://wa.me/2348100866322"
URL_CBT_PRO       = "https://cssadewale.github.io/cbt-system"

CONTACT_PHONE     = "+234 810 086 6322"
CONTACT_EMAIL     = "hello@hmgconcepts.com"

# ── Palette (used in CSS + Plotly) ────────────────────────────────────────────
COLOR_PRIMARY     = "#1A56DB"   # HMG blue
COLOR_ACCENT      = "#F5A623"   # warm amber
COLOR_DARK        = "#0F1923"   # sidebar background
COLOR_DARK_2      = "#1E2B3C"
COLOR_TEXT_MUTED  = "#6B8FAF"
COLOR_SUCCESS     = "#27AE60"
COLOR_DANGER      = "#E74C3C"


# ══════════════════════════════════════════════════════════════════════════════
# HTML helpers
# ══════════════════════════════════════════════════════════════════════════════
def sidebar_header_html() -> str:
    return f"""
    <div style="text-align:center;padding:14px 0 16px;">
      <div style="font-size:30px;">{PRODUCT_EMOJI}</div>
      <div style="color:#fff;font-size:17px;font-weight:800;letter-spacing:.3px;">
        {PRODUCT_NAME}
      </div>
      <div style="color:{COLOR_TEXT_MUTED};font-size:9px;margin-top:2px;
                  text-transform:uppercase;letter-spacing:.6px;">
        by {VENDOR}
      </div>
    </div>
    """

def sidebar_footer_html() -> str:
    return f"""
    <div style="margin-top:14px;text-align:center;color:#2D4560;
                font-size:9px;line-height:1.5;">
      <div style="color:{COLOR_TEXT_MUTED};font-weight:600;">
        {PARENT_BRAND} · {VENDOR}
      </div>
      <div style="margin-top:3px;">{PRODUCT_VERSION} · Built in {LOCATION}</div>
      <div style="margin-top:6px;">
        <a href="{URL_CONCEPTS}" target="_blank"
           style="color:{COLOR_TEXT_MUTED};text-decoration:none;">hmgconcepts</a> ·
        <a href="{URL_ACADEMY}" target="_blank"
           style="color:{COLOR_TEXT_MUTED};text-decoration:none;">academy</a> ·
        <a href="{URL_FOUNDER}" target="_blank"
           style="color:{COLOR_TEXT_MUTED};text-decoration:none;">founder</a>
      </div>
    </div>
    """

def about_card_html() -> str:
    return f"""
    <div style="background:linear-gradient(135deg,#F0F4FF,#FFF7E8);
                border:1px solid #DCE8FF;border-radius:14px;
                padding:18px 20px;margin-top:12px;">
      <div style="font-size:11px;color:{COLOR_PRIMARY};font-weight:700;
                  text-transform:uppercase;letter-spacing:.8px;">
        About {PRODUCT_NAME}
      </div>
      <div style="font-size:14px;color:#1F2937;font-weight:700;margin-top:4px;">
        {PRODUCT_TAGLINE}
      </div>
      <div style="font-size:12px;color:#4B5563;margin-top:8px;line-height:1.55;">
        Built by <b>{VENDOR}</b>, the EdTech arm of <b>{PARENT_BRAND}</b>
        (est. {FOUNDED_YEAR}), to give Nigerian secondary schools a
        professional-grade timetable engine — constraint-aware, exam-aware,
        substitution-aware, and PDF-ready.
      </div>
      <div style="font-size:11px;color:#6B7280;margin-top:10px;font-style:italic;">
        "{PARENT_TAGLINE}"
      </div>
      <div style="font-size:11px;color:#4B5563;margin-top:14px;">
        <b>Designed & Engineered by</b> {FOUNDER_NAME} —
        <i>{FOUNDER_TITLE}</i>
      </div>
      <div style="margin-top:10px;font-size:11px;">
        <a href="{URL_CONCEPTS}" target="_blank"
           style="color:{COLOR_PRIMARY};text-decoration:none;margin-right:10px;">
           🌐 HMG Concepts</a>
        <a href="{URL_ACADEMY}" target="_blank"
           style="color:{COLOR_PRIMARY};text-decoration:none;margin-right:10px;">
           🎓 HMG Academy</a>
        <a href="{URL_FOUNDER}" target="_blank"
           style="color:{COLOR_PRIMARY};text-decoration:none;margin-right:10px;">
           👤 Founder</a>
        <a href="{URL_WHATSAPP}" target="_blank"
           style="color:{COLOR_PRIMARY};text-decoration:none;">💬 WhatsApp</a>
      </div>
    </div>
    """

def footer_credit_text() -> str:
    return (
        f"{PRODUCT_NAME} {PRODUCT_VERSION} — {VENDOR} "
        f"(a subsidiary of {PARENT_BRAND}) · "
        f"Built by {FOUNDER_NAME} · {LOCATION}"
    )
