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
def build_claude_prompt(results):
    date = results.get("report_date", "Unknown")
    lines = []
    lines.append(f"FLEET SALES REPORT — Period Ending {date}")
    lines.append("=" * 60)
    lines.append("\nREGIONAL SUMMARY (from Region report):")
    for r in results["region_summary"][:20]:
        tag = " ← FLEET-WIDE TOTAL. Use this figure directly for any total-fleet-volume statement. Do not add up National/East/West/Inside East/Inside West/Aggregators or any other rows to recompute this yourself." if r["label"] == "Fleet Hierarchy" else ""
        lines.append(
            f"  {r['label']} | Rep: {r['salesperson'] or 'N/A'} | "
            f"Current: {fmt_num(r['current_week'], 'GAL')} | "
            f"13Wk Avg: {fmt_num(r['avg_13wk'], 'GAL')} | "
            f"vs Avg: {fmt_pct(r['curr_ov_avg'])} | "
            f"WoW: {fmt_pct(r['wow_pct'])}{tag}"
        )

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

    if has_regular:
        lines.append(f"\nFUEL DECREASE ALERTS — MAIN ACCOUNTS, REGULAR REGIONS (>=10,000 GAL avg, >=5,000 GAL current): {len(regular_main)} flagged")
        for a in regular_main[:75]:
            lines.append(
                f"  [{a['bucket']}] {a['customer']} | Region: {a['region']} | "
                f"Rep: {a['salesperson'] or 'N/A'} | Mgr: {a['area_manager'] or 'N/A'} | "
                f"This week: {fmt_num(a['current_week'], 'GAL')} | "
                f"Prior: {fmt_num(a['prior_week'], 'GAL')} | "
                f"Change: {fmt_pct(a['wow_pct'])} ({fmt_num(a['vol_change'], 'GAL')} vol)"
            )
        lines.append(f"\nFUEL DECREASE ALERTS — SECONDARY ACCOUNTS, REGULAR REGIONS (<10,000 GAL avg): {len(regular_secondary)} flagged")
        for a in regular_secondary[:100]:
            lines.append(
                f"  [{a['bucket']}] {a['customer']} | Region: {a['region']} | "
                f"Rep: {a['salesperson'] or 'N/A'} | Mgr: {a['area_manager'] or 'N/A'} | "
                f"This week: {fmt_num(a['current_week'], 'GAL')} | "
                f"Prior: {fmt_num(a['prior_week'], 'GAL')} | "
                f"Change: {fmt_pct(a['wow_pct'])} ({fmt_num(a['vol_change'], 'GAL')} vol)"
            )

    if has_inside:
        inside_tiered = []
        for a in inside_main + inside_secondary:
            tier = gal_tier(a["vol_change"])
            if tier is None:
                continue
            a_copy = dict(a)
            a_copy["gal_tier"] = tier
            inside_tiered.append(a_copy)
        inside_tiered.sort(key=lambda x: x["vol_change"])

        lines.append(f"\nFUEL DECREASE ALERTS — INSIDE SALES REGIONS (tiered by GAL lost, not percentage; sorted largest loss first; under 100 GAL excluded; percentage intentionally omitted -- do not calculate or mention WoW% for these accounts): {len(inside_tiered)} flagged")
        for a in inside_tiered[:100]:
            lines.append(
                f"  [{a['gal_tier']}] {a['customer']} | Region: {a['region']} | "
                f"Rep: {a['salesperson'] or 'N/A'} | Mgr: {a['area_manager'] or 'N/A'} | "
                f"This week: {fmt_num(a['current_week'], 'GAL')} | "
                f"Prior: {fmt_num(a['prior_week'], 'GAL')} | "
                f"Vol Change: {fmt_num(a['vol_change'], 'GAL')}"
            )

    lines.append(f"\nNEWLY DARK ACCOUNTS (13wk avg >= 1,000 GAL, zero this period): {len(results['fuel_newly_dark'])} accounts")
    for a in results["fuel_newly_dark"]:
        lines.append(
            f"  {a['customer']} | Region: {a['region']} | "
            f"Rep: {a['salesperson'] or 'N/A'} | Mgr: {a['area_manager'] or 'N/A'} | "
            f"13Wk Avg: {fmt_num(a['avg_13wk'], 'GAL')} | "
            f"Last Known Vol: {fmt_num(a['last_known_vol'], 'GAL')}"
        )

    regular_increases = [a for a in results["fuel_increases"] if not is_inside_sales(a["region"])]
    inside_increases = [a for a in results["fuel_increases"] if is_inside_sales(a["region"])]

    if has_regular:
        lines.append(f"\nFUEL INCREASES — REGULAR REGIONS (sorted by volume gained): {len(regular_increases)} accounts")
        for a in regular_increases[:100]:
            wow_display = "N/A (returning from near-zero)" if a.get("suppress_pct") else fmt_pct(a['wow_pct'])
            lines.append(
                f"  {a['customer']} | Region: {a['region']} | "
                f"Rep: {a['salesperson'] or 'N/A'} | "
                f"This week: {fmt_num(a['current_week'], 'GAL')} | "
                f"Prior: {fmt_num(a['prior_week'], 'GAL')} | "
                f"WoW: {wow_display} | Vol gained: {fmt_num(a['vol_change'], 'GAL')}"
            )

    if has_inside:
        lines.append(f"\nFUEL INCREASES — INSIDE SALES REGIONS (sorted by volume gained; percentage intentionally omitted -- do not calculate or mention WoW% for these accounts): {len(inside_increases)} accounts")
        for a in inside_increases[:100]:
            lines.append(
                f"  {a['customer']} | Region: {a['region']} | "
                f"Rep: {a['salesperson'] or 'N/A'} | "
                f"This week: {fmt_num(a['current_week'], 'GAL')} | "
                f"Prior: {fmt_num(a['prior_week'], 'GAL')} | "
                f"Vol gained: {fmt_num(a['vol_change'], 'GAL')}"
            )

    for metric, alerts in results["non_fuel_alerts"].items():
        unit = METRIC_UNITS.get(metric, "")
        lines.append(f"\n{metric.upper()} ALERTS (significant unit change): {len(alerts)} flagged")
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
        section_4_scope = "This upload contains BOTH regular regions and Inside Sales regions. Include both subsections below."
        regular_block = """### Regular Regions
Group by bucket: 20-30%, then 10-20%, then 0-10%.
#### 20-30% Decrease
Table: Account | Region | Rep | Area Manager | This Week | Prior Week | WoW Change | Vol Change
#### 10-20% Decrease
Same table format.
#### 0-10% Decrease
Same table format.
"""
        inside_block = """### Inside Sales Regions
These are smaller-fleet regions where percentage swings are misleading -- a single truck can look like a 60% drop. Grouped by gallons lost instead, largest loss first within each tier. Do NOT include a WoW Change / percentage column anywhere in this subsection -- these accounts have no percentage data provided and none should be shown or calculated.
#### Tier 1 — 1,500+ GAL Lost
Table: Account | Region | Rep | Area Manager | This Week | Prior Week | Vol Change
#### Tier 2 — 500-1,499 GAL Lost
Same table format.
#### Tier 3 — 100-499 GAL Lost
Same table format.
"""
    elif has_inside:
        section_4_scope = "This upload contains ONLY Inside Sales regions. Do NOT create a 'Regular Regions' subsection or heading at all -- go straight to the tiered GAL format below as the only content in this section, with no 'Inside Sales Regions' sub-heading needed either since it's the only content."
        regular_block = ""
        inside_block = """These are smaller-fleet regions where percentage swings are misleading -- a single truck can look like a 60% drop. Grouped by gallons lost instead, largest loss first within each tier. Do NOT include a WoW Change / percentage column anywhere -- these accounts have no percentage data provided and none should be shown or calculated.
#### Tier 1 — 1,500+ GAL Lost
Table: Account | Region | Rep | Area Manager | This Week | Prior Week | Vol Change
#### Tier 2 — 500-1,499 GAL Lost
Same table format.
#### Tier 3 — 100-499 GAL Lost
Same table format.
"""
    else:
        section_4_scope = "This upload contains ONLY regular regions. Do NOT create an 'Inside Sales Regions' subsection or heading at all."
        regular_block = """Group by bucket: 20-30%, then 10-20%, then 0-10%.
#### 20-30% Decrease
Table: Account | Region | Rep | Area Manager | This Week | Prior Week | WoW Change | Vol Change
#### 10-20% Decrease
Same table format.
#### 0-10% Decrease
Same table format.
"""
        inside_block = ""

    if has_regular and has_inside:
        section_5_scope = "This upload contains BOTH regular and Inside Sales regions."
        increases_regular_block = """### Regular Regions
Table: Account | Region | Rep | This Week | Prior Week | WoW Change | Vol Gained
Sorted by absolute volume gained. If WoW reads "N/A (returning from near-zero)", display as "—".
"""
        increases_inside_block = """### Inside Sales Regions
Table: Account | Region | Rep | This Week | Prior Week | Vol Gained
Do NOT include a WoW Change / percentage column -- sorted by absolute volume gained only.
"""
    elif has_inside:
        section_5_scope = "This upload contains ONLY Inside Sales regions. Do NOT include a WoW Change / percentage column anywhere in this section."
        increases_regular_block = ""
        increases_inside_block = """Table: Account | Region | Rep | This Week | Prior Week | Vol Gained
Sorted by absolute volume gained only, no percentage column.
"""
    else:
        section_5_scope = "This upload contains ONLY regular regions."
        increases_regular_block = """Table: Account | Region | Rep | This Week | Prior Week | WoW Change | Vol Gained
Sorted by absolute volume gained. If WoW reads "N/A (returning from near-zero)", display as "—".
"""
        increases_inside_block = ""

    prompt += f"""

---
INSTRUCTIONS:
You are the Fleet Sales Intelligence Agent for Love's Travel Stops fleet sales team. Using the structured data provided above, generate a professional executive insight summary for SVP-level leadership.

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

OUTPUT FORMAT -- follow this exact order:

## FLEET SALES INTELLIGENCE BRIEF
**Period Ending: [DATE]**

## 1. OPENING
2-3 bullet points. Total fuel volume vs. rolling average. Standout regional trend. National performance direction.

## 2. REGIONAL HIGHLIGHTS
### Top 3 Performing Regions
Table with columns: Rank | Region | Rep | Current Volume | WoW Change | vs. 13Wk Avg
After table: 2-3 bullets with context on what's driving each region's performance.

### Bottom 3 Underperforming Regions
Same table format.
After table: 2-3 bullets with context on which accounts are driving underperformance in each region.

## 3. NEWLY DARK ACCOUNTS
Table with columns: Account | Region | Rep | Area Manager | 13Wk Avg | This Week | Last Known Volume
The This Week column should show 0 GAL for every row. State it plainly.
After table: 2-3 bullets noting patterns in regions or reps with multiple dark accounts.

## 4. FUEL DECREASE ALERTS
{section_4_scope}
{regular_block}{inside_block}
After all included subsections above: 2-3 bullets noting rep or region concentration.

## 5. FUEL INCREASES
{section_5_scope}
{increases_regular_block}{increases_inside_block}
After table(s): 2-3 bullets with top volume gainers.

## 6. NON-FUEL HIGHLIGHTS
For each metric (Tires, PM, TCE Spend per Truck, Labor Hours), 2-3 bullets covering steepest movers.

## 7. KEY TAKEAWAYS
3 bullets. Each names a specific account or rep, states a specific number, surfaces an observation.

## 8. CLOSING
One sentence. Factual only.

DATA CONTEXT:
- Main accounts: 13-week average >= 10,000 GAL and current week >= 5,000 GAL
- Secondary accounts: below those thresholds
- Newly dark: accounts with 13-week avg >= 1,000 GAL reporting zero this period
- Regular-region decrease buckets: 0-10%, 10-20%, 20-30%. Inside Sales region decreases are NOT percentage-bucketed -- they are tiered by absolute GAL lost (Tier 1: >=1,500 GAL, Tier 2: 500-1,499 GAL, Tier 3: 100-499 GAL) and sorted largest loss to smallest, with anything under 100 GAL excluded entirely, and no percentage shown. In both cases, accounts moving more than 30% in either direction are intentionally excluded -- those are covered by a separate fleet exception report.
- Fuel increases follow the same percentage rule as decreases: regular regions show WoW%, Inside Sales regions never show or calculate a percentage for any account, in any section.
- In the REGIONAL SUMMARY data, the row marked "FLEET-WIDE TOTAL" is the correct total fleet volume figure -- quote it directly, do not sum other rows yourself.
- If a field shows N/A, omit it rather than displaying N/A
- If no accounts cross a threshold in a section that IS included, write "No alerts this period" under that specific subsection heading -- but never create a subsection heading for a region type that is entirely absent from this upload.
- Never fabricate data. Only report what is in the provided data.
"""
    return prompt

def
