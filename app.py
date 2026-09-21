import streamlit as st
import tempfile
import os
import anthropic
import httpx2
from PIL import Image

# ── Page config ────────────────────────────────────────────────────────────────
try:
    icon = Image.open("loveslogo.webp")
except Exception:
    icon = "🚛"

st.set_page_config(
    page_title="Fleet Sales Intelligence — Love's",
    page_icon=icon,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 0 !important; max-width: 1200px; }

.loves-header {
    background: white;
    border-bottom: 3px solid #d90d0d;
    padding: 14px 32px;
    display: flex;
    align-items: center;
    gap: 20px;
    margin: -1rem -1rem 0 -1rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.loves-header-title { font-weight: 700; font-size: 16px; color: #1a1a1a; }
.loves-header-title span { color: #d90d0d; }
.loves-header-badge {
    margin-left: auto;
    background: #f2ce1b;
    color: #5a4000;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    padding: 4px 12px;
    border-radius: 20px;
}
.loves-banner {
    background: #d90d0d;
    color: rgba(255,255,255,0.9);
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 8px 32px;
    margin: 0 -1rem 2rem -1rem;
}
.eyebrow {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    color: #d90d0d;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
}
.eyebrow::before {
    content: '';
    display: inline-block;
    width: 24px;
    height: 3px;
    background: #f2ce1b;
    border-radius: 2px;
}
.stat-row { display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
.stat-card {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 18px 16px;
    border-top: 4px solid #e0e0e0;
    flex: 1;
    min-width: 140px;
}
.stat-card.danger { border-top-color: #d90d0d; }
.stat-card.good { border-top-color: #1a8a4a; }
.stat-card.warning { border-top-color: #f2ce1b; }
.stat-value { font-size: 26px; font-weight: 800; line-height: 1; margin-bottom: 6px; color: #1a1a1a; }
.stat-card.danger .stat-value { color: #d90d0d; }
.stat-card.good .stat-value { color: #1a8a4a; }
.stat-label { font-size: 12px; color: #666; font-weight: 500; }
.analysis-card {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 28px 32px;
    margin-bottom: 16px;
}
.card-label {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    color: #d90d0d;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 10px;
}
.card-label::before {
    content: '';
    display: inline-block;
    width: 20px;
    height: 3px;
    background: #f2ce1b;
    border-radius: 2px;
}
.stButton > button {
    background: #d90d0d !important;
    color: white !important;
    border: none !important;
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 800 !important;
    font-size: 14px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    border-radius: 8px !important;
    padding: 12px 24px !important;
    width: 100% !important;
}
.stButton > button:hover { background: #a80a0a !important; }
.stTabs [data-baseweb="tab-list"] {
    background: white;
    border: 1.5px solid #e0e0e0;
    border-radius: 10px;
    padding: 4px;
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Montserrat', sans-serif;
    font-weight: 700;
    font-size: 13px;
    border-radius: 7px;
    padding: 10px 24px;
}
.stTabs [aria-selected="true"] {
    background: #d90d0d !important;
    color: white !important;
}
.results-title { font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }
.results-title span { color: #d90d0d; }
</style>
""", unsafe_allow_html=True)

# ── Imports from existing modules ───────────────────────────────────────────────
from analyzer import analyze_reports
from monthly_analyzer import analyze_monthly_report
from config import METRIC_UNITS, MAX_TOKENS, INSIDE_SALES_REGIONS

# ── API Key ─────────────────────────────────────────────────────────────────────
def get_api_key():
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        from config import ANTHROPIC_API_KEY
        return ANTHROPIC_API_KEY

# ── Formatting helpers ──────────────────────────────────────────────────────────
def fmt_pct(val):
    if val is None:
        return "N/A"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.1f}%"

def fmt_num(val, unit=""):
    if val is None:
        return "N/A"
    if unit == "$":
        return f"${val:,.2f}"
    return f"{val:,.0f}{' ' + unit if unit else ''}"

def is_inside_sales(region):
    return str(region).split(".")[0] in INSIDE_SALES_REGIONS

def gal_tier(vol_change):
    abs_vol = abs(vol_change)
    if abs_vol >= 1500:
        return "Tier 1 (1,500+ GAL Lost)"
    elif abs_vol >= 500:
        return "Tier 2 (500-1,499 GAL Lost)"
    elif abs_vol >= 100:
        return "Tier 3 (100-499 GAL Lost)"
    return None

# ── Prompt builders ─────────────────────────────────────────────────────────────
def md_table(headers, rows):
    if not rows:
        return "No alerts this period."
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def build_claude_prompt(results):
    date = results.get("report_date", "Unknown")
    lines = []
    lines.append(f"FLEET SALES REPORT — Period Ending {date}")
    lines.append("=" * 60)

    table_map = {}

    fleet_total_row = next((r for r in results["region_summary"] if r["label"] == "Fleet Hierarchy"), None)
    fleet_total_line = ""
    if fleet_total_row and fleet_total_row["current_week"]:
        fleet_total_line = f"FLEET-WIDE TOTAL FUEL VOLUME (use this exact figure for any total-fleet-volume statement, do not recompute): {fmt_num(fleet_total_row['current_week'], 'GAL')}, WoW: {fmt_pct(fleet_total_row['wow_pct'])}"
    lines.append(f"\n{fleet_total_line}" if fleet_total_line else "\nFLEET-WIDE TOTAL: not available (no Region report data for this figure).")

    valid_regions = [
        r for r in results["region_summary"]
        if r["label"] and r["label"].startswith("Sales Region")
        and r["current_week"] is not None and r["wow_pct"] is not None
    ]
    seen_labels = set()
    distinct_regions = []
    for r in valid_regions:
        if r["label"] not in seen_labels:
            seen_labels.add(r["label"])
            distinct_regions.append(r)

    has_region_data = bool(distinct_regions)
    if has_region_data:
        ranked = sorted(distinct_regions, key=lambda x: x["wow_pct"], reverse=True)
        top3 = ranked[:3]
        bottom3 = list(reversed(ranked[-3:])) if len(ranked) >= 3 else list(reversed(ranked))
        table_map["%%TOP3_TABLE%%"] = md_table(
            ["Rank", "Region", "Rep", "Current Volume", "WoW Change", "vs. 13Wk Avg"],
            [[i + 1, r["label"], r["salesperson"] or "N/A", fmt_num(r["current_week"], "GAL"), fmt_pct(r["wow_pct"]), fmt_pct(r["curr_ov_avg"])] for i, r in enumerate(top3)]
        )
        table_map["%%BOTTOM3_TABLE%%"] = md_table(
            ["Rank", "Region", "Rep", "Current Volume", "WoW Change", "vs. 13Wk Avg"],
            [[i + 1, r["label"], r["salesperson"] or "N/A", fmt_num(r["current_week"], "GAL"), fmt_pct(r["wow_pct"]), fmt_pct(r["curr_ov_avg"])] for i, r in enumerate(bottom3)]
        )
        lines.append(f"\nFor context only (do not use to build a table yourself): {len(distinct_regions)} distinct regions have region-level data this period.")
    else:
        lines.append("\nNo region-level totals were provided in the source data this period (customer-only upload) -- there is no Top 3 / Bottom 3 regional table this period.")

    regular_main = [a for a in results["fuel_main_alerts"] if not is_inside_sales(a["region"])]
    inside_main = [a for a in results["fuel_main_alerts"] if is_inside_sales(a["region"])]
    regular_secondary = [a for a in results["fuel_secondary"] if not is_inside_sales(a["region"])]
    inside_secondary = [a for a in results["fuel_secondary"] if is_inside_sales(a["region"])]

    all_accounts_for_scope = (
        results["fuel_main_alerts"] + results["fuel_secondary"]
        + results["fuel_increases"] + results["fuel_newly_dark"]
    )
    has_regular = any(not is_inside_sales(a["region"]) for a in all_accounts_for_scope)
    has_inside = any(is_inside_sales(a["region"]) for a in all_accounts_for_scope)

    dec_headers = ["Account", "Region", "Rep", "Area Manager", "This Week", "Prior Week", "WoW Change", "Vol Change"]

    def dec_row(a):
        return [a["customer"], a["region"], a["salesperson"] or "N/A", a["area_manager"] or "N/A",
                fmt_num(a["current_week"], "GAL"), fmt_num(a["prior_week"], "GAL"),
                fmt_pct(a["wow_pct"]), fmt_num(a["vol_change"], "GAL")]

    if has_regular:
        regular_all = regular_main + regular_secondary
        b2030 = sorted([a for a in regular_all if a["bucket"] == "20-30% Decrease"], key=lambda x: x["vol_change"])
        b1020 = sorted([a for a in regular_all if a["bucket"] == "10-20% Decrease"], key=lambda x: x["vol_change"])
        b010 = sorted([a for a in regular_all if a["bucket"] == "0-10% Decrease"], key=lambda x: x["vol_change"])
        table_map["%%REG_DEC_2030%%"] = md_table(dec_headers, [dec_row(a) for a in b2030])
        table_map["%%REG_DEC_1020%%"] = md_table(dec_headers, [dec_row(a) for a in b1020])
        table_map["%%REG_DEC_010%%"] = md_table(dec_headers, [dec_row(a) for a in b010])
        lines.append(f"\nFor context only: {len(b2030)} regular-region accounts in 20-30% decrease, {len(b1020)} in 10-20%, {len(b010)} in 0-10%.")

    if has_inside:
        inside_tiered = []
        for a in inside_main + inside_secondary:
            tier = gal_tier(a["vol_change"])
            if tier is None:
                continue
            a_copy = dict(a)
            a_copy["gal_tier"] = tier
            inside_tiered.append(a_copy)
        t1 = sorted([a for a in inside_tiered if a["gal_tier"].startswith("Tier 1")], key=lambda x: x["vol_change"])
        t2 = sorted([a for a in inside_tiered if a["gal_tier"].startswith("Tier 2")], key=lambda x: x["vol_change"])
        t3 = sorted([a for a in inside_tiered if a["gal_tier"].startswith("Tier 3")], key=lambda x: x["vol_change"])
        inside_dec_headers = ["Account", "Region", "Rep", "Area Manager", "This Week", "Prior Week", "Vol Change"]

        def inside_dec_row(a):
            return [a["customer"], a["region"], a["salesperson"] or "N/A", a["area_manager"] or "N/A",
                    fmt_num(a["current_week"], "GAL"), fmt_num(a["prior_week"], "GAL"),
                    fmt_num(a["vol_change"], "GAL")]

        table_map["%%INS_DEC_T1%%"] = md_table(inside_dec_headers, [inside_dec_row(a) for a in t1])
        table_map["%%INS_DEC_T2%%"] = md_table(inside_dec_headers, [inside_dec_row(a) for a in t2])
        table_map["%%INS_DEC_T3%%"] = md_table(inside_dec_headers, [inside_dec_row(a) for a in t3])
        lines.append(f"\nFor context only: {len(t1)} Inside Sales accounts in Tier 1, {len(t2)} in Tier 2, {len(t3)} in Tier 3.")

    table_map["%%DARK_TABLE%%"] = md_table(
        ["Account", "Region", "Rep", "Area Manager", "13Wk Avg", "This Week", "Last Known Volume"],
        [[a['customer'], a['region'], a['salesperson'] or 'N/A', a['area_manager'] or 'N/A', fmt_num(a['avg_13wk'], 'GAL'), '0 GAL', fmt_num(a['last_known_vol'], 'GAL')] for a in results['fuel_newly_dark']]
    )
    lines.append(f"\nFor context only: {len(results['fuel_newly_dark'])} newly dark accounts this period.")
    for a in results["fuel_newly_dark"]:
        lines.append(f"  DARK: {a['customer']} | Region: {a['region']} | Rep: {a['salesperson'] or 'N/A'} | 13Wk Avg: {fmt_num(a['avg_13wk'], 'GAL')} | Last Known: {fmt_num(a['last_known_vol'], 'GAL')}")

    regular_increases = sorted([a for a in results["fuel_increases"] if not is_inside_sales(a["region"])], key=lambda x: x["vol_change"], reverse=True)
    inside_increases = sorted([a for a in results["fuel_increases"] if is_inside_sales(a["region"])], key=lambda x: x["vol_change"], reverse=True)

    if has_regular:
        def inc_row(a):
            wow_display = "N/A (returning from near-zero)" if a.get("suppress_pct") else fmt_pct(a['wow_pct'])
            return [a["customer"], a["region"], a["salesperson"] or "N/A",
                    fmt_num(a["current_week"], "GAL"), fmt_num(a["prior_week"], "GAL"),
                    wow_display, fmt_num(a["vol_change"], "GAL")]
        table_map["%%REG_INC_TABLE%%"] = md_table(['Account', 'Region', 'Rep', 'This Week', 'Prior Week', 'WoW Change', 'Vol Gained'], [inc_row(a) for a in regular_increases])
        lines.append(f"\nFor context only: {len(regular_increases)} regular-region fuel increase accounts.")
        for a in regular_increases:
            lines.append(f"  INCREASE (regular): {a['customer']} | Region: {a['region']} | Rep: {a['salesperson'] or 'N/A'} | Vol gained: {fmt_num(a['vol_change'], 'GAL')}")

    if has_inside:
        def inc_row_inside(a):
            return [a["customer"], a["region"], a["salesperson"] or "N/A",
                    fmt_num(a["current_week"], "GAL"), fmt_num(a["prior_week"], "GAL"),
                    fmt_num(a["vol_change"], "GAL")]
        table_map["%%INS_INC_TABLE%%"] = md_table(['Account', 'Region', 'Rep', 'This Week', 'Prior Week', 'Vol Gained'], [inc_row_inside(a) for a in inside_increases])
        lines.append(f"\nFor context only: {len(inside_increases)} Inside Sales fuel increase accounts.")
        for a in inside_increases:
            lines.append(f"  INCREASE (inside sales): {a['customer']} | Region: {a['region']} | Rep: {a['salesperson'] or 'N/A'} | Vol gained: {fmt_num(a['vol_change'], 'GAL')}")

    for metric, alerts in results["non_fuel_alerts"].items():
        unit = METRIC_UNITS.get(metric, "")
        lines.append(f"\n{metric.upper()} ALERTS (significant unit change, use PLAIN TEXT numbers only, no backticks, no code formatting): {len(alerts)} flagged")
        for a in alerts[:15]:
            lines.append(
                f"  [{a['direction'].upper()}] {a['customer']} | "
                f"Rep: {a['salesperson'] or 'N/A'} | "
                f"Current: {fmt_num(a['current_week'], unit)} | "
                f"Prior: {fmt_num(a['prior_week'], unit)} | "
                f"Change: {fmt_num(int(a['current_week'] - a['prior_week']), unit)}"
            )
    if results["errors"]:
        lines.append("\nERRORS DURING PROCESSING:")
        for e in results["errors"]:
            lines.append(f"  {e}")
    prompt = "\n".join(lines)

    if has_regular and has_inside:
        section_4_scope = "This upload contains BOTH regular regions and Inside Sales regions."
        section_4_headings = "### Regular Regions\n#### 20-30% Decrease\nOn its own line, output exactly: %%REG_DEC_2030%%\n#### 10-20% Decrease\nOn its own line, output exactly: %%REG_DEC_1020%%\n#### 0-10% Decrease\nOn its own line, output exactly: %%REG_DEC_010%%\n\n### Inside Sales Regions\n#### Tier 1 — 1,500+ GAL Lost\nOn its own line, output exactly: %%INS_DEC_T1%%\n#### Tier 2 — 500-1,499 GAL Lost\nOn its own line, output exactly: %%INS_DEC_T2%%\n#### Tier 3 — 100-499 GAL Lost\nOn its own line, output exactly: %%INS_DEC_T3%%"
    elif has_inside:
        section_4_scope = "This upload contains ONLY Inside Sales regions. Do not create a 'Regular Regions' heading."
        section_4_headings = "#### Tier 1 — 1,500+ GAL Lost\nOn its own line, output exactly: %%INS_DEC_T1%%\n#### Tier 2 — 500-1,499 GAL Lost\nOn its own line, output exactly: %%INS_DEC_T2%%\n#### Tier 3 — 100-499 GAL Lost\nOn its own line, output exactly: %%INS_DEC_T3%%"
    else:
        section_4_scope = "This upload contains ONLY regular regions. Do not create an 'Inside Sales Regions' heading."
        section_4_headings = "#### 20-30% Decrease\nOn its own line, output exactly: %%REG_DEC_2030%%\n#### 10-20% Decrease\nOn its own line, output exactly: %%REG_DEC_1020%%\n#### 0-10% Decrease\nOn its own line, output exactly: %%REG_DEC_010%%"

    if has_regular and has_inside:
        section_5_headings = "### Regular Regions\nOn its own line, output exactly: %%REG_INC_TABLE%%\n\n### Inside Sales Regions\nOn its own line, output exactly: %%INS_INC_TABLE%%"
    elif has_inside:
        section_5_headings = "On its own line, output exactly: %%INS_INC_TABLE%%\nDo not create a 'Regular Regions' heading."
    else:
        section_5_headings = "On its own line, output exactly: %%REG_INC_TABLE%%\nDo not create an 'Inside Sales Regions' heading."

    top3_instruction = "On its own line, output exactly: %%TOP3_TABLE%%" if has_region_data else "No table this period -- write 1-2 sentences instead, based on the account-level context above, making clear region-level totals were not available."
    bottom3_instruction = "On its own line, output exactly: %%BOTTOM3_TABLE%%" if has_region_data else "No table this period -- skip straight to 2-3 bullets using account-level data, do not repeat the Top 3 note."

    prompt += f"""

---
INSTRUCTIONS:
You are the Fleet Sales Intelligence Agent for Love's Travel Stops fleet sales team. Generate a professional executive insight summary for SVP-level leadership.

ABSOLUTE RULE ON TABLES -- READ CAREFULLY: You do not have the ability to build correct tables yourself in this report, and you must not try. Every place a table belongs, this document tells you to output one exact placeholder token (formatted like %%SOMETHING%%) on its own line, by itself, with nothing else on that line -- no table, no pipes, no dashes, no columns, nothing you compose yourself. That token will be swapped for the real table automatically after you respond. If you write anything other than the bare token on that line -- including a table you construct yourself, extra columns, or a percentage -- it will be visibly wrong in the final report and it will be your error. The "for context only" data given to you elsewhere in this prompt is for writing your bullet commentary ONLY -- never use it to build a table, and never use it to calculate a percentage for any Inside Sales account under any circumstances, even though you can see the numbers to do so.

TONE AND STYLE:
- Write as a senior analyst. Direct, confident, factual.
- Present information as observations and insights -- not directives or prescriptions.
- Never tell leadership what to do or how to respond. Surface the data and let them draw conclusions.
- Never call out gaps, failures, or accountability issues. State facts neutrally.
- Never write: "it is worth noting", "as we can see", "it appears that", "please note", "requires immediate action", "should follow up", "accountability gap"
- State decreases plainly: "down 21.4% week-over-week"
- Frame increases as signals: "up 18% -- strongest week in the 13-week window"
- Numbers must always include units (GAL, EA, $, Hrs)
- Reference area manager alongside salesperson when available
- Keep sections tight -- no extra blank lines between sections, no padding
- Minimize bold formatting. Use bold only for section headers, never for account names, rep names, metrics, or numbers in the text.
- Never use backticks or code formatting anywhere in your response, for any reason, under any circumstances.

OUTPUT FORMAT -- follow this exact order:

## FLEET SALES INTELLIGENCE BRIEF
**Period Ending: [DATE]**

## 1. OPENING
2-3 bullet points. Total fuel volume vs. rolling average (use the FLEET-WIDE TOTAL figure given above verbatim, do not recompute it). Standout regional trend. National performance direction.

## 2. REGIONAL HIGHLIGHTS
### Top 3 Performing Regions
{top3_instruction}
After (table token or sentences): 2-3 bullets with context on what's driving each region's performance.

### Bottom 3 Underperforming Regions
{bottom3_instruction}
After (table token or bullets): 2-3 bullets with context on which accounts are driving underperformance in each region.

## 3. NEWLY DARK ACCOUNTS
On its own line, output exactly: %%DARK_TABLE%%
After table token: 2-3 bullets noting patterns in regions or reps with multiple dark accounts.

## 4. FUEL DECREASE ALERTS
{section_4_scope}
{section_4_headings}
After all table tokens above: 2-3 bullets noting rep or region concentration.

## 5. FUEL INCREASES
{section_5_headings}
After table token(s): 2-3 bullets with top volume gainers.

## 6. NON-FUEL HIGHLIGHTS
For each metric (Tires, PM, TCE Spend per Truck, Labor Hours), 2-3 bullets covering steepest movers. Write all numbers as plain text, no backticks, no code formatting, single $ sign for dollar amounts (e.g. $1,750.00).

## 7. KEY TAKEAWAYS
3 bullets. Each names a specific account or rep, states a specific number, surfaces an observation.

## 8. CLOSING
One sentence. Factual only.

DATA CONTEXT:
- Main accounts: 13-week average >= 10,000 GAL and current week >= 5,000 GAL
- Secondary accounts: below those thresholds
- Newly dark: accounts with 13-week avg >= 1,000 GAL reporting zero this period
- Accounts moving more than 30% in either direction are intentionally excluded -- those are covered by a separate fleet exception report.
- Never fabricate data.
"""
    return prompt, table_map

def build_monthly_prompt(results):
    period = results.get("period", "Unknown")
    window = results.get("trend_window", 4)
    months = results.get("trend_months", [])
    month_str = ", ".join([m for m in months if m]) if months else "recent months"
    lines = []
    lines.append(f"MONTHLY FLEET SALES REPORT — Period {period}")
    lines.append("=" * 60)
    lines.append("\nREGIONAL ROLLUP (DSL gallons, YOY, profit, price per gallon):")
    for r in results["regional"][:40]:
        lines.append(
            f"  {r['label']} | Rep: {r['rep'] or 'N/A'} | "
            f"DSL: {fmt_num(r['dsl'], 'GAL')} | "
            f"YOY: {fmt_pct(r['yoy_pct'])} | "
            f"Profit: {fmt_num(r['profit'], '$')} | "
            f"PPG: {fmt_num(r['ppg'], '$')} | "
            f"Tires: {fmt_num(r['tires'], 'EA')} | PM: {fmt_num(r['pm'], 'EA')} | "
            f"Labor: {fmt_num(r['labor'], 'Hrs')}"
        )
    lines.append("\nAREA MANAGER PERFORMANCE (ranked by DSL volume):")
    for m in results["area_managers"][:25]:
        lines.append(
            f"  {m['manager']} | Group: {m['group'] or 'N/A'} | "
            f"DSL: {fmt_num(m['dsl'], 'GAL')} | YOY: {fmt_pct(m['yoy_pct'])}"
        )
    lines.append(f"\nMULTI-MONTH TREND — consecutive monthly decline across the recent {window}-month window ({month_str}): {len(results['trend_declining'])} accounts")
    for t in results["trend_declining"][:30]:
        lines.append(
            f"  {t['customer']} | Region: {t['region']} | "
            f"4 Months Ago: {fmt_num(t['window_start'], 'GAL')} | "
            f"Most recent month: {fmt_num(t['recent_month'], 'GAL')} | "
            f"Decline: {fmt_pct(t['drop_pct'])} ({fmt_num(t['drop_vol'], 'GAL')})"
        )
    if results["errors"]:
        lines.append("\nERRORS DURING PROCESSING:")
        for e in results["errors"]:
            lines.append(f"  {e}")
    prompt = "\n".join(lines)
    prompt += f"""

---
INSTRUCTIONS:
You are the Fleet Sales Intelligence Agent for Love's Travel Stops fleet sales team. Using the structured monthly data above, generate a professional executive insight summary for SVP-level leadership. This is a MONTHLY report for {period} -- use monthly language throughout, never weekly.

TONE AND STYLE:
- Write as a senior analyst. Direct, confident, factual.
- Never tell leadership what to do or how to respond.
- Never write: "it is worth noting", "as we can see", "it appears that", "please note", "requires immediate action"
- State declines plainly: "down 9.1% year-over-year"
- Numbers must always include units (GAL, $, EA, Hrs)
- Minimize bold formatting. Use bold only for section headers.

OUTPUT FORMAT:

## MONTHLY FLEET SALES BRIEF
**Period: {period}**

## 1. OPENING
2-3 bullets. Total fleet hierarchy volume and YOY direction. Overall profit picture. Clearest field group headline.

## 2. REGIONAL PERFORMANCE
### Top 3 Regions by Year-over-Year Growth
Table: Rank | Region | Rep | DSL Volume | YOY | Profit | PPG
After table: 2-3 bullets with context.

### Bottom 3 Regions by Year-over-Year Change
Same table format. After table: 2-3 bullets.

## 3. AREA MANAGER PERFORMANCE
Table: Rank | Area Manager | Group | DSL Volume | YOY
After table: 2-3 bullets covering top managers and notable YOY movement.

## 4. MULTI-MONTH TREND
Table: Account | Region | 4 Months Ago | Most Recent Month | Decline % | Volume Lost
This reflects only the recent {window}-month window ({month_str}).
After table: 2-3 bullets on largest declines and region concentration.

## 5. PROFIT & MARGIN
2-3 bullets. Highest and lowest profit regions, PPG spread. Factual only.

## 6. KEY TAKEAWAYS
3 bullets. Each names a specific region/account/manager, states a number, surfaces an observation.

## 7. CLOSING
One sentence. Factual only.

DATA CONTEXT:
- This is monthly data. YOY is reliable -- use it confidently.
- Multi-month trend reflects ONLY the recent {window}-month window, only accounts that declined every month starting at or above 25,000 GAL.
- PPG is price/profit per gallon in dollars.
- Never fabricate data.
"""
    return prompt


# ── Header ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="loves-header">
    <div class="loves-header-title">Fleet Sales <span>Intelligence</span></div>
    <div class="loves-header-badge">Powered by Claude Opus</div>
</div>
<div class="loves-banner">
    ● Fleet Sales Analysis Portal &nbsp;&nbsp; ● Internal Use Only &nbsp;&nbsp; ● AI Powered
</div>
""", unsafe_allow_html=True)

# ── Session state ───────────────────────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None
if "analysis" not in st.session_state:
    st.session_state.analysis = None
if "mode" not in st.session_state:
    st.session_state.mode = None
if "summary" not in st.session_state:
    st.session_state.summary = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ── Upload UI ───────────────────────────────────────────────────────────────────
if st.session_state.analysis is None:
    st.markdown('<div class="eyebrow">Analysis Portal</div>', unsafe_allow_html=True)
    st.markdown("## Fleet Intelligence for Love's Sales Team")
    st.markdown("Choose an analysis type, upload your report, and get an executive-ready insight summary in seconds.")

    tab_weekly, tab_monthly = st.tabs(["Weekly Analysis", "Monthly Analysis"])

    with tab_weekly:
        st.markdown("#### Upload Reports")
        col1, col2 = st.columns(2)
        with col1:
            customer_file = st.file_uploader("Customer Report", type=["xlsx", "xls"], key="customer_upload", help="13 Week Trend Report by Customer")
        with col2:
            region_file = st.file_uploader("Region Report", type=["xlsx", "xls"], key="region_upload", help="13 Week Trend Report by Region")

        ready = customer_file is not None or region_file is not None
        if st.button("ANALYZE REPORTS", disabled=not ready, key="btn_weekly"):
            customer_path = None
            region_path = None
            try:
                if customer_file:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as cf:
                        cf.write(customer_file.read())
                        customer_path = cf.name
                if region_file:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as rf:
                        rf.write(region_file.read())
                        region_path = rf.name

                with st.spinner("Analyzing your report... this takes about 60 seconds."):
                    results = analyze_reports(customer_path, region_path)
                    prompt, table_map = build_claude_prompt(results)
                    client = anthropic.Anthropic(
                        api_key=get_api_key(),
                        http_client=httpx2.Client(verify=False)
                    )
                    message = client.messages.create(
                        model="claude-opus-4-6",
                        max_tokens=MAX_TOKENS,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    claude_output = message.content[0].text
                    for token, table_text in table_map.items():
                        claude_output = claude_output.replace(token, table_text)

                valid_regions = [r for r in results["region_summary"] if r["wow_pct"] is not None and r["current_week"] is not None and r["label"] and r["label"].startswith("Sales Region") and (r["current_week"] or 0) >= 1000000]
                regions_sorted = sorted(valid_regions, key=lambda x: x["wow_pct"], reverse=True)
                best_region = regions_sorted[0] if regions_sorted else None
                worst_region = regions_sorted[-1] if len(regions_sorted) > 1 else None
                fleet_total = next((r for r in results["region_summary"] if r["label"] == "Fleet Hierarchy"), None)
                national_volume = fleet_total["current_week"] if fleet_total and fleet_total["current_week"] else 0
                national_prior = fleet_total["prior_week"] if fleet_total and fleet_total["prior_week"] else 0
                national_wow = ((national_volume - national_prior) / national_prior * 100) if national_prior else 0

                st.session_state.results = results
                st.session_state.analysis = claude_output
                st.session_state.mode = "weekly"
                st.session_state.summary = {
                    "report_date": results["report_date"],
                    "best_region_name": best_region.get("label", "N/A") if best_region else "N/A",
                    "best_region_wow": best_region.get("wow_pct", 0) if best_region else 0,
                    "worst_region_name": worst_region.get("label", "N/A") if worst_region else "N/A",
                    "worst_region_wow": worst_region.get("wow_pct", 0) if worst_region else 0,
                    "national_volume": national_volume,
                    "national_wow": national_wow,
                    "region_count": len(results["region_summary"]),
                    "newly_dark_count": len(results["fuel_newly_dark"]),
                }
                st.session_state.chat_history = []
                st.rerun()

            except Exception as e:
                st.error(f"Analysis failed: {str(e)}")
            finally:
                for p in [customer_path, region_path]:
                    if p:
                        try:
                            os.unlink(p)
                        except Exception:
                            pass

    with tab_monthly:
        st.markdown("#### Upload Report")
        monthly_file = st.file_uploader("Monthly Sales Report", type=["xlsx", "xls"], key="monthly_upload", help="Full monthly report with rollups and 13-month history")

        ready_m = monthly_file is not None
        if st.button("ANALYZE REPORT", disabled=not ready_m, key="btn_monthly"):
            monthly_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as mf:
                    mf.write(monthly_file.read())
                    monthly_path = mf.name

                with st.spinner("Analyzing your report... this takes about 60 seconds."):
                    results = analyze_monthly_report(monthly_path)
                    prompt = build_monthly_prompt(results)
                    client = anthropic.Anthropic(
                        api_key=get_api_key(),
                        http_client=httpx2.Client(verify=False)
                    )
                    message = client.messages.create(
                        model="claude-opus-4-6",
                        max_tokens=MAX_TOKENS,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    claude_output = message.content[0].text

                st.session_state.results = results
                st.session_state.analysis = claude_output
                st.session_state.mode = "monthly"
                st.session_state.summary = {
                    "period": results["period"],
                    "region_count": len(results["regional"]),
                    "manager_count": len(results["area_managers"]),
                    "declining_count": len(results["trend_declining"]),
                    "trend_window": results["trend_window"],
                }
                st.session_state.chat_history = []
                st.rerun()

            except Exception as e:
                st.error(f"Analysis failed: {str(e)}")
            finally:
                if monthly_path:
                    try:
                        os.unlink(monthly_path)
                    except Exception:
                        pass

# ── Results UI ──────────────────────────────────────────────────────────────────
else:
    s = st.session_state.summary
    results = st.session_state.results
    analysis = st.session_state.analysis
    mode = st.session_state.mode

    col_title, col_btn = st.columns([4, 1])
    with col_title:
        period_label = s.get("report_date") or s.get("period") or ""
        st.markdown(f'<div class="results-title">Fleet Sales <span>Insights</span> &nbsp;<small style="font-size:13px;color:#666;font-family:\'DM Mono\',monospace;font-weight:400;">Period {period_label}</small></div>', unsafe_allow_html=True)
    with col_btn:
        if st.button("New Analysis"):
            st.session_state.results = None
            st.session_state.analysis = None
            st.session_state.mode = None
            st.session_state.summary = None
            st.session_state.chat_history = []
            st.rerun()

    st.markdown("<hr style='border:none;border-top:3px solid #d90d0d;margin:8px 0 20px 0;'>", unsafe_allow_html=True)

    if mode == "weekly":
        best_wow = f"+{s['best_region_wow']:.1f}%" if s['best_region_wow'] > 0 else f"{s['best_region_wow']:.1f}%"
        worst_wow = f"+{s['worst_region_wow']:.1f}%" if s['worst_region_wow'] > 0 else f"{s['worst_region_wow']:.1f}%"
        nat_vol = f"{s['national_volume']/1e6:.1f}M GAL" if s['national_volume'] else "N/A"
        st.markdown(f"""
        <div class="stat-row">
            <div class="stat-card good"><div class="stat-value">{s['best_region_name']}</div><div class="stat-label">Best Region WoW ({best_wow})</div></div>
            <div class="stat-card danger"><div class="stat-value">{s['worst_region_name']}</div><div class="stat-label">Worst Region WoW ({worst_wow})</div></div>
            <div class="stat-card"><div class="stat-value">{nat_vol}</div><div class="stat-label">Total Fleet Volume</div></div>
            <div class="stat-card"><div class="stat-value">{s['region_count']}</div><div class="stat-label">Regions Tracked</div></div>
            <div class="stat-card danger"><div class="stat-value">{s['newly_dark_count']}</div><div class="stat-label">Newly Dark Accounts</div></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="stat-row">
            <div class="stat-card"><div class="stat-value">{s['region_count']}</div><div class="stat-label">Regions</div></div>
            <div class="stat-card"><div class="stat-value">{s['manager_count']}</div><div class="stat-label">Area Managers</div></div>
            <div class="stat-card danger"><div class="stat-value">{s['declining_count']}</div><div class="stat-label">Declining Accounts ({s['trend_window']}-Mo Window)</div></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="analysis-card"><div class="card-label">Executive Insight Summary</div>', unsafe_allow_html=True)
    st.markdown(analysis.replace(chr(96), "").replace("$", "\\$"))
    st.markdown('</div>', unsafe_allow_html=True)

    period_label = s.get("report_date") or s.get("period") or "report"
    st.download_button(
        label="Download Analysis as Text",
        data=analysis,
        file_name=f"fleet_analysis_{period_label}.txt",
        mime="text/plain"
    )

    import pandas as pd

    if mode == "weekly" and results.get("fuel_main_alerts"):
        st.markdown('<div class="analysis-card"><div class="card-label">Top Fuel Decrease Alerts — Main Accounts</div>', unsafe_allow_html=True)
        alert_data = []
        for a in results["fuel_main_alerts"][:20]:
            alert_data.append({
                "Account": a["customer"],
                "Region": a["region"] or "—",
                "Rep": a["salesperson"] or "—",
                "Area Manager": a["area_manager"] or "—",
                "This Week": fmt_num(a["current_week"], "GAL"),
                "Prior Week": fmt_num(a["prior_week"], "GAL"),
                "WoW Change": fmt_pct(a["wow_pct"]),
                "Vol Change": fmt_num(a["vol_change"], "GAL"),
                "Bucket": a["bucket"] or "—",
            })
        st.dataframe(pd.DataFrame(alert_data), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

    if mode == "monthly" and results.get("trend_declining"):
        st.markdown('<div class="analysis-card"><div class="card-label">Declining Accounts — Recent Multi-Month Window</div>', unsafe_allow_html=True)
        trend_data = []
        for t in results["trend_declining"][:30]:
            trend_data.append({
                "Account": t["customer"],
                "Region": t["region"] or "—",
                "4 Months Ago": fmt_num(t["window_start"], "GAL"),
                "Most Recent Month": fmt_num(t["recent_month"], "GAL"),
                "Decline %": fmt_pct(t["drop_pct"]),
                "Volume Lost": fmt_num(t["drop_vol"], "GAL"),
            })
        st.dataframe(pd.DataFrame(trend_data), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Follow-up chat ──────────────────────────────────────────────────────────
    st.markdown('<div class="analysis-card"><div class="card-label">Ask a Follow-Up Question</div>', unsafe_allow_html=True)

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if question := st.chat_input("Ask about the data — e.g. which rep has the most newly dark accounts?"):
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    client = anthropic.Anthropic(
                        api_key=get_api_key(),
                        http_client=httpx2.Client(verify=False)
                    )
                    message = client.messages.create(
                        model="claude-opus-4-6",
                        max_tokens=1024,
                        messages=[{
                            "role": "user",
                            "content": f"""You are the Fleet Sales Intelligence Agent for Love's Travel Stops. A user has already run an analysis and is asking a follow-up question.

ANALYSIS CONTEXT:
{analysis}

USER QUESTION:
{question}

Answer concisely and factually based only on the data provided. Use specific numbers. Do not fabricate data."""
                        }]
                    )
                    answer = message.content[0].text
                    st.write(answer)
                    st.session_state.chat_history.append({"role": "assistant", "content": answer})
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    st.markdown('</div>', unsafe_allow_html=True)
