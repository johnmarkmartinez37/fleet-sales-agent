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
from ttc_analyzer import analyze_ttc_reports
from ttc_prompt import build_ttc_prompt
from fuel_prompt import build_claude_prompt, fmt_pct, fmt_num
from alignment import parse_alignment, find_saved_alignment
from email_builder import (
    build_fuel_items, build_ttc_items, estimate_cost, actual_cost,
    generate_all, finalize_item, package_zip, _safe_date,
)
from config import METRIC_UNITS, MAX_TOKENS, INSIDE_SALES_REGIONS, TTC_MANAGER_DISPLAY, INSIDE_EAST_REGIONS, INSIDE_WEST_REGIONS

# ── API Key ─────────────────────────────────────────────────────────────────────
def get_api_key():
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        from config import ANTHROPIC_API_KEY
        return ANTHROPIC_API_KEY

def show_df(df):
    """st.dataframe that works on both older and newer Streamlit versions."""
    try:
        st.dataframe(df, width="stretch", hide_index=True)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True)


def show_html_preview(page_html, height=700):
    """Render an email preview. The HTML is built by email_builder with every piece of text escaped."""
    if hasattr(st, "iframe"):
        st.iframe(page_html, height=height)
    else:
        import streamlit.components.v1 as components
        components.html(page_html, height=height, scrolling=True)


def get_filterable_regions(results):
    regions = set()
    for a in results["fuel_main_alerts"] + results["fuel_secondary"] + results["fuel_increases"] + results["fuel_newly_dark"]:
        if a.get("region"):
            regions.add(a["region"])
    for alerts in results["non_fuel_alerts"].values():
        for a in alerts:
            if a.get("region"):
                regions.add(a["region"])

    def region_sort_key(r):
        try:
            return (0, float(r))
        except (TypeError, ValueError):
            return (1, str(r))

    return sorted(regions, key=region_sort_key)


def filter_results_by_region(results, region):
    return {
        "report_date": results["report_date"],
        "region_summary": [],
        "fuel_main_alerts": [a for a in results["fuel_main_alerts"] if a.get("region") == region],
        "fuel_secondary": [a for a in results["fuel_secondary"] if a.get("region") == region],
        "fuel_newly_dark": [a for a in results["fuel_newly_dark"] if a.get("region") == region],
        "fuel_increases": [a for a in results["fuel_increases"] if a.get("region") == region],
        "non_fuel_alerts": {
            metric: [a for a in alerts if a.get("region") == region]
            for metric, alerts in results["non_fuel_alerts"].items()
        },
        "errors": [],
    }


def filter_results_by_region_group(results, region_set):
    def in_group(a):
        return str(a.get("region")).split(".")[0] in region_set
    return {
        "report_date": results["report_date"],
        "region_summary": [],
        "fuel_main_alerts": [a for a in results["fuel_main_alerts"] if in_group(a)],
        "fuel_secondary": [a for a in results["fuel_secondary"] if in_group(a)],
        "fuel_newly_dark": [a for a in results["fuel_newly_dark"] if in_group(a)],
        "fuel_increases": [a for a in results["fuel_increases"] if in_group(a)],
        "non_fuel_alerts": {
            metric: [a for a in alerts if in_group(a)]
            for metric, alerts in results["non_fuel_alerts"].items()
        },
        "errors": [],
    }


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
if "available_regions" not in st.session_state:
    st.session_state.available_regions = ["Overall (All Regions)"]
if "selected_view" not in st.session_state:
    st.session_state.selected_view = "Overall (All Regions)"
if "region_analyses" not in st.session_state:
    st.session_state.region_analyses = {}
if "ttc_results" not in st.session_state:
    st.session_state.ttc_results = None
if "ttc_available_managers" not in st.session_state:
    st.session_state.ttc_available_managers = ["Overall (All Managers)"]
if "ttc_selected_view" not in st.session_state:
    st.session_state.ttc_selected_view = "Overall (All Managers)"
if "ttc_analyses" not in st.session_state:
    st.session_state.ttc_analyses = {}
if "email_plan" not in st.session_state:
    st.session_state.email_plan = None
if "email_outputs" not in st.session_state:
    st.session_state.email_outputs = {}

# ── Upload UI ───────────────────────────────────────────────────────────────────
if st.session_state.mode is None:
    st.markdown('<div class="eyebrow">Analysis Portal</div>', unsafe_allow_html=True)
    st.markdown("## Fleet Intelligence for Love's Sales Team")
    st.markdown("Choose an analysis type, upload your report, and get an executive-ready insight summary in seconds.")

    tab_weekly, tab_monthly, tab_ttc, tab_email = st.tabs(["Weekly Analysis", "Monthly Analysis", "Truck Care Analysis", "Email Automation"])

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
                filterable = get_filterable_regions(results)
                available = ["Overall (All Regions)"]
                if any(str(r).split(".")[0] in INSIDE_EAST_REGIONS for r in filterable):
                    available.append("Inside East")
                if any(str(r).split(".")[0] in INSIDE_WEST_REGIONS for r in filterable):
                    available.append("Inside West")
                available += filterable
                st.session_state.available_regions = available
                st.session_state.selected_view = "Overall (All Regions)"
                st.session_state.region_analyses = {"Overall (All Regions)": claude_output}
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

    with tab_ttc:
        st.markdown("#### Upload Reports")
        st.markdown("Customer and Region reports are required. The Monthly Sales Report is optional -- upload it only once it's re-exported each month; it adds Profit/PPG, the new-vs-retread tire split, and a 13-month trend view, labeled with its own period, without replacing any of the current-week numbers below.")
        col1, col2 = st.columns(2)
        with col1:
            ttc_customer_file = st.file_uploader("Customer Report (TTC)", type=["xlsx", "xls"], key="ttc_customer_upload", help="13 Week Trend Report by Customer (Truck Care)")
        with col2:
            ttc_region_file = st.file_uploader("Region Report (TTC)", type=["xlsx", "xls"], key="ttc_region_upload", help="13 Week Trend Report by Region (Truck Care)")
        ttc_monthly_file = st.file_uploader("Monthly Sales Report (optional)", type=["xlsx", "xls"], key="ttc_monthly_upload", help="Re-exported monthly -- adds Profit/PPG, tire-type split, and 13-month trend")

        ttc_ready = ttc_customer_file is not None and ttc_region_file is not None
        if st.button("ANALYZE REPORTS", disabled=not ttc_ready, key="btn_ttc"):
            ttc_customer_path = None
            ttc_region_path = None
            ttc_monthly_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as cf:
                    cf.write(ttc_customer_file.read())
                    ttc_customer_path = cf.name
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as rf:
                    rf.write(ttc_region_file.read())
                    ttc_region_path = rf.name
                if ttc_monthly_file:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as mf:
                        mf.write(ttc_monthly_file.read())
                        ttc_monthly_path = mf.name

                with st.spinner("Analyzing Truck Care reports... this takes about 60 seconds."):
                    ttc_results = analyze_ttc_reports(ttc_customer_path, ttc_region_path, ttc_monthly_path)
                    overall_prompt, overall_table_map = build_ttc_prompt("Overall (All Managers)", ttc_results)
                    client = anthropic.Anthropic(
                        api_key=get_api_key(),
                        http_client=httpx2.Client(verify=False)
                    )
                    overall_message = client.messages.create(
                        model="claude-opus-4-6",
                        max_tokens=MAX_TOKENS,
                        messages=[{"role": "user", "content": overall_prompt}]
                    )
                    overall_output = overall_message.content[0].text
                    for token, table_text in overall_table_map.items():
                        overall_output = overall_output.replace(token, table_text)

                st.session_state.ttc_results = ttc_results
                st.session_state.mode = "truck_care"
                st.session_state.ttc_available_managers = ["Overall (All Managers)", "Brett Moody", "Keith Taggart", "TJ Atwood"]
                st.session_state.ttc_selected_view = "Overall (All Managers)"
                st.session_state.ttc_analyses = {"Overall (All Managers)": overall_output}
                st.session_state.chat_history = []
                st.rerun()

            except Exception as e:
                st.error(f"Analysis failed: {str(e)}")
            finally:
                for p in [ttc_customer_path, ttc_region_path, ttc_monthly_path]:
                    if p:
                        try:
                            os.unlink(p)
                        except Exception:
                            pass

    with tab_email:
        st.markdown("#### Build Emails")
        st.markdown("Upload the weekly reports and the Region Alignments file. You will see every recipient and subject line before any brief is generated. Nothing is emailed from this page -- it produces files for the Power Automate flow.")
        col1, col2 = st.columns(2)
        with col1:
            em_fuel_file = st.file_uploader("Fuel Customer Report", type=["xlsx", "xls"], key="em_fuel_upload", help="13 Week Trend Report by Customer (fuel)")
        with col2:
            em_align_file = st.file_uploader("Region Alignments (optional)", type=["xlsx", "xls"], key="em_align_upload", help="Only needed when the alignments changed. Otherwise the copy saved with the app is used.")
            try:
                saved_alignment_path = find_saved_alignment(os.path.dirname(os.path.abspath(__file__)))
                saved_alignment_error = None
            except ValueError as ex:
                saved_alignment_path, saved_alignment_error = None, str(ex)
            if em_align_file is not None:
                st.caption("Using the file you just uploaded for this run.")
            elif saved_alignment_path:
                st.caption(f"Using the saved alignment file: {os.path.basename(saved_alignment_path)}")
            elif saved_alignment_error:
                st.error(saved_alignment_error)
            else:
                st.warning("No saved alignment file found. Upload one, or save Region_Alignments.xlsx in the GitHub repo.")
        st.markdown("**Truck Care (optional)** -- upload both Truck Care reports to include the three TTC manager emails.")
        col3, col4 = st.columns(2)
        with col3:
            em_ttc_customer_file = st.file_uploader("Customer Report (TTC)", type=["xlsx", "xls"], key="em_ttc_customer_upload")
        with col4:
            em_ttc_region_file = st.file_uploader("Region Report (TTC)", type=["xlsx", "xls"], key="em_ttc_region_upload")
        em_ttc_monthly_file = st.file_uploader("Monthly Sales Report (optional)", type=["xlsx", "xls"], key="em_ttc_monthly_upload")

        ttc_pair_ok = (em_ttc_customer_file is None) == (em_ttc_region_file is None)
        if not ttc_pair_ok:
            st.warning("Upload both Truck Care reports (Customer and Region), or neither.")
        em_ready = em_fuel_file is not None and (em_align_file is not None or saved_alignment_path is not None) and ttc_pair_ok

        if st.button("BUILD EMAIL PLAN", disabled=not em_ready, key="btn_email_plan"):
            em_paths = []

            def save_upload(f):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tf:
                    tf.write(f.read())
                    em_paths.append(tf.name)
                    return tf.name

            try:
                with st.spinner("Building the email plan... (no AI calls are made in this step)"):
                    fuel_path = save_upload(em_fuel_file)
                    align_path = save_upload(em_align_file) if em_align_file is not None else saved_alignment_path
                    fuel_results = analyze_reports(fuel_path, None)
                    if fuel_results["errors"]:
                        raise ValueError("; ".join(fuel_results["errors"]))
                    alignment = parse_alignment(align_path)
                    plan_items, plan_skipped = build_fuel_items(fuel_results, alignment)
                    plan_date = fuel_results["report_date"] or "Unknown"

                    if em_ttc_customer_file is not None and em_ttc_region_file is not None:
                        ttc_c_path = save_upload(em_ttc_customer_file)
                        ttc_r_path = save_upload(em_ttc_region_file)
                        ttc_m_path = save_upload(em_ttc_monthly_file) if em_ttc_monthly_file else None
                        ttc_email_results = analyze_ttc_reports(ttc_c_path, ttc_r_path, ttc_m_path)
                        if ttc_email_results["errors"]:
                            raise ValueError("; ".join(ttc_email_results["errors"]))
                        plan_items += build_ttc_items(ttc_email_results, ttc_email_results.get("report_date") or plan_date)

                st.session_state.email_plan = {"items": plan_items, "skipped": plan_skipped, "report_date": plan_date}
                st.session_state.email_outputs = {}
                st.session_state.mode = "emails"
                st.rerun()

            except Exception as e:
                st.error(f"Could not build the email plan: {str(e)}")
            finally:
                for p in em_paths:
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

# ── Email automation UI ─────────────────────────────────────────────────────────
elif st.session_state.mode == "emails":
    import pandas as pd

    plan = st.session_state.email_plan
    em_items = plan["items"]
    em_skipped = plan["skipped"]
    em_date = plan["report_date"]

    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.markdown(
            f'<div class="results-title">Email <span>Automation</span> &nbsp;<small style="font-size:13px;color:#666;font-family:\'DM Mono\',monospace;font-weight:400;">Period {em_date}</small></div>',
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button("Start Over", key="btn_email_back"):
            st.session_state.mode = None
            st.session_state.email_plan = None
            st.session_state.email_outputs = {}
            st.rerun()
    st.markdown("<hr style='border:none;border-top:3px solid #d90d0d;margin:8px 0 20px 0;'>", unsafe_allow_html=True)

    est = estimate_cost(em_items)
    n_warn = sum(1 for i in em_items if i["warnings"])
    st.markdown(f"""
    <div class="stat-row">
        <div class="stat-card"><div class="stat-value">{len(em_items)}</div><div class="stat-label">Emails Planned</div></div>
        <div class="stat-card"><div class="stat-value">{len(em_skipped)}</div><div class="stat-label">Skipped</div></div>
        <div class="stat-card warning"><div class="stat-value">{n_warn}</div><div class="stat-label">With Notes</div></div>
        <div class="stat-card"><div class="stat-value">${est['typical']:.2f}</div><div class="stat-label">Est. Cost (up to ${est['high']:.2f})</div></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("##### Recipients (review before generating)")
    show_df(pd.DataFrame([{
        "Email": i["label"],
        "To": i["to"] or "—",
        "CC": "; ".join(i["cc"]) or "—",
        "Subject": i["subject"],
        "Flagged accounts": i["flagged"],
        "Notes": "; ".join(i["warnings"]) or "—",
    } for i in em_items]))

    if em_skipped:
        with st.expander(f"Not emailed ({len(em_skipped)})"):
            show_df(pd.DataFrame([{"Email": s_["email"], "Reason": s_["reason"]} for s_ in em_skipped]))

    st.markdown("##### Test mode")
    test_mode = st.checkbox("Address every email to me instead of the real recipients (subject gets a [TEST] prefix)", value=True, key="em_test_mode")
    test_address = None
    if test_mode:
        typed = st.text_input("Send test emails to", key="em_test_address", placeholder="firstname.lastname@loves.com").strip()
        if "@" in typed and "." in typed.split("@")[-1]:
            test_address = typed
        else:
            st.info("Enter your email address to package test files.")
    else:
        st.warning("LIVE MODE: the files you download will email the real reps and Area Managers once they land in the SharePoint folder.")

    st.markdown("##### Generate briefs")
    st.caption(f"Makes {len(em_items)} Claude calls (about {est['input_tokens']:,} input tokens in total). Estimated cost ${est['typical']:.2f}, up to about ${est['high']:.2f}. Takes a few minutes.")
    if st.button("GENERATE BRIEFS", key="btn_generate_briefs"):
        try:
            gen_client = anthropic.Anthropic(
                api_key=get_api_key(),
                http_client=httpx2.Client(verify=False)
            )
            bar = st.progress(0.0, text="Starting...")

            def on_progress(done, total, label):
                bar.progress(done / total, text=f"{done} of {total} done (latest: {label})")

            st.session_state.email_outputs = generate_all(em_items, gen_client, on_progress)
            bar.empty()
        except Exception as e:
            st.error(f"Generation failed: {str(e)}")

    em_outputs = st.session_state.email_outputs
    if em_outputs:
        ok_ids = [i["id"] for i in em_items if em_outputs.get(i["id"], {}).get("status") == "ok"]
        bad = [i for i in em_items if i["id"] not in ok_ids]
        used_in = sum(o["in_tokens"] for o in em_outputs.values())
        used_out = sum(o["out_tokens"] for o in em_outputs.values())
        st.success(f"{len(ok_ids)} of {len(em_items)} briefs generated. Actual cost: ${actual_cost(used_in, used_out):.2f} ({used_in:,} in / {used_out:,} out tokens).")
        for i in bad:
            st.error(f"{i['label']}: " + "; ".join(em_outputs.get(i["id"], {}).get("warnings", ["not generated"])))
        for i in em_items:
            w = em_outputs.get(i["id"], {}).get("warnings", []) if i["id"] in ok_ids else []
            if w:
                st.warning(f"{i['label']}: " + "; ".join(w))

        if test_mode and not test_address:
            st.info("Enter your test address above to package the files.")
        elif ok_ids:
            zip_bytes = package_zip(em_items, em_outputs, em_skipped, em_date, test_address)
            st.download_button(
                label="Download send-ready ZIP",
                data=zip_bytes,
                file_name=f"fleet_emails_{_safe_date(em_date)}{'_TEST' if test_mode else ''}.zip",
                mime="application/zip",
                key="download_email_zip",
            )
            st.caption("Upload ONLY the .json files from the 'send' folder to the SharePoint folder your flow watches. The 'preview' folder is for you to open in a browser.")

            ok_items = [i for i in em_items if i["id"] in ok_ids]
            pick = st.selectbox("Preview an email", [i["label"] for i in ok_items], key="em_preview_pick")
            chosen = next(i for i in ok_items if i["label"] == pick)
            payload = finalize_item(chosen, em_outputs[chosen["id"]], em_date, test_address)
            show_html_preview(payload["_preview"])

# ── Results UI ──────────────────────────────────────────────────────────────────
else:
    mode = st.session_state.mode
    s = st.session_state.summary if mode in ("weekly", "monthly") else None

    col_title, col_btn = st.columns([4, 1])
    with col_title:
        if mode == "truck_care":
            title_text = "Truck Care <span>Insights</span>"
        else:
            title_text = "Fleet Sales <span>Insights</span>"
            period_label = s.get("report_date") or s.get("period") or ""
            title_text += f' &nbsp;<small style="font-size:13px;color:#666;font-family:\'DM Mono\',monospace;font-weight:400;">Period {period_label}</small>'
        st.markdown(f'<div class="results-title">{title_text}</div>', unsafe_allow_html=True)
    with col_btn:
        if st.button("New Analysis"):
            st.session_state.results = None
            st.session_state.analysis = None
            st.session_state.mode = None
            st.session_state.summary = None
            st.session_state.chat_history = []
            st.session_state.available_regions = ["Overall (All Regions)"]
            st.session_state.selected_view = "Overall (All Regions)"
            st.session_state.region_analyses = {}
            st.session_state.ttc_results = None
            st.session_state.ttc_available_managers = ["Overall (All Managers)"]
            st.session_state.ttc_selected_view = "Overall (All Managers)"
            st.session_state.ttc_analyses = {}
            st.rerun()

    st.markdown("<hr style='border:none;border-top:3px solid #d90d0d;margin:8px 0 20px 0;'>", unsafe_allow_html=True)

    if mode == "weekly":
        results = st.session_state.results
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
    elif mode == "monthly":
        results = st.session_state.results
        st.markdown(f"""
        <div class="stat-row">
            <div class="stat-card"><div class="stat-value">{s['region_count']}</div><div class="stat-label">Regions</div></div>
            <div class="stat-card"><div class="stat-value">{s['manager_count']}</div><div class="stat-label">Area Managers</div></div>
            <div class="stat-card danger"><div class="stat-value">{s['declining_count']}</div><div class="stat-label">Declining Accounts ({s['trend_window']}-Mo Window)</div></div>
        </div>
        """, unsafe_allow_html=True)
    elif mode == "truck_care":
        ttc_results = st.session_state.ttc_results
        roster_size = len(ttc_results.get("roster", {}))
        monthly_note = ttc_results.get("monthly", {}).get("period") if ttc_results.get("monthly") else "Not uploaded"
        total_flagged = sum(
            len(v) for mgr in ttc_results.get("flagged_customers", {}).values() for v in mgr.values()
        )
        st.markdown(f"""
        <div class="stat-row">
            <div class="stat-card"><div class="stat-value">3</div><div class="stat-label">Managers Tracked</div></div>
            <div class="stat-card"><div class="stat-value">{roster_size}</div><div class="stat-label">Reps in Roster</div></div>
            <div class="stat-card danger"><div class="stat-value">{total_flagged}</div><div class="stat-label">Flagged Customer Movers</div></div>
            <div class="stat-card"><div class="stat-value">{monthly_note}</div><div class="stat-label">Monthly Data Period</div></div>
        </div>
        """, unsafe_allow_html=True)

    if mode == "weekly":
        col_select, col_spacer = st.columns([2, 3])
        with col_select:
            selected_view = st.selectbox(
                "View summary for:",
                st.session_state.available_regions,
                index=st.session_state.available_regions.index(st.session_state.selected_view)
                if st.session_state.selected_view in st.session_state.available_regions else 0,
                key="region_view_selector"
            )
        st.session_state.selected_view = selected_view

        if selected_view not in st.session_state.region_analyses:
            with st.spinner(f"Building summary for {selected_view}... this takes about 30-60 seconds."):
                if selected_view == "Inside East":
                    filtered = filter_results_by_region_group(results, INSIDE_EAST_REGIONS)
                elif selected_view == "Inside West":
                    filtered = filter_results_by_region_group(results, INSIDE_WEST_REGIONS)
                else:
                    filtered = filter_results_by_region(results, selected_view)
                region_prompt, region_table_map = build_claude_prompt(filtered)
                client = anthropic.Anthropic(
                    api_key=get_api_key(),
                    http_client=httpx2.Client(verify=False)
                )
                region_message = client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=MAX_TOKENS,
                    messages=[{"role": "user", "content": region_prompt}]
                )
                region_output = region_message.content[0].text
                for token, table_text in region_table_map.items():
                    region_output = region_output.replace(token, table_text)
                st.session_state.region_analyses[selected_view] = region_output

        analysis = st.session_state.region_analyses[selected_view]
    elif mode == "truck_care":
        ttc_results = st.session_state.ttc_results
        col_select, col_spacer = st.columns([2, 3])
        with col_select:
            ttc_selected_view = st.selectbox(
                "View summary for:",
                st.session_state.ttc_available_managers,
                index=st.session_state.ttc_available_managers.index(st.session_state.ttc_selected_view)
                if st.session_state.ttc_selected_view in st.session_state.ttc_available_managers else 0,
                format_func=lambda m: TTC_MANAGER_DISPLAY.get(m, m),
                key="ttc_view_selector"
            )
        st.session_state.ttc_selected_view = ttc_selected_view

        if ttc_selected_view not in st.session_state.ttc_analyses:
            display_name = TTC_MANAGER_DISPLAY.get(ttc_selected_view, ttc_selected_view)
            with st.spinner(f"Building summary for {display_name}... this takes about 30-60 seconds."):
                mgr_prompt, mgr_table_map = build_ttc_prompt(ttc_selected_view, ttc_results)
                client = anthropic.Anthropic(
                    api_key=get_api_key(),
                    http_client=httpx2.Client(verify=False)
                )
                mgr_message = client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=MAX_TOKENS,
                    messages=[{"role": "user", "content": mgr_prompt}]
                )
                mgr_output = mgr_message.content[0].text
                for token, table_text in mgr_table_map.items():
                    mgr_output = mgr_output.replace(token, table_text)
                st.session_state.ttc_analyses[ttc_selected_view] = mgr_output

        analysis = st.session_state.ttc_analyses[ttc_selected_view]
    else:
        analysis = st.session_state.analysis

    st.markdown('<div class="analysis-card"><div class="card-label">Executive Insight Summary</div>', unsafe_allow_html=True)
    st.markdown(analysis.replace(chr(96), "").replace("$", "\\$"))
    st.markdown('</div>', unsafe_allow_html=True)

    if mode == "truck_care":
        download_label = TTC_MANAGER_DISPLAY.get(st.session_state.ttc_selected_view, st.session_state.ttc_selected_view)
        st.download_button(
            label="Download Analysis as Text",
            data=analysis,
            file_name=f"truck_care_analysis_{download_label.replace(' ', '_')}.txt",
            mime="text/plain",
            key=f"download_ttc_{st.session_state.get('ttc_selected_view', 'x')}"
        )
    else:
        period_label = s.get("report_date") or s.get("period") or "report"
        view_suffix = f"_{st.session_state.selected_view}" if mode == "weekly" else ""
        st.download_button(
            label="Download Analysis as Text",
            data=analysis,
            file_name=f"fleet_analysis_{period_label}{view_suffix}.txt",
            mime="text/plain",
            key=f"download_{st.session_state.get('selected_view', 'x')}"
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
