
import streamlit as st
import tempfile
import os
import anthropic
import httpx
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
from config import METRIC_UNITS, MAX_TOKENS
 
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
 
# ── Prompt builders ─────────────────────────────────────────────────────────────
def build_claude_prompt(results):
    date = results.get("report_date", "Unknown")
    lines = []
    lines.append(f"FLEET SALES REPORT — Period Ending {date}")
    lines.append("=" * 60)
    lines.append("\nREGIONAL SUMMARY (from Region report):")
    for r in results["region_summary"][:20]:
        lines.append(
            f"  {r['label']} | Rep: {r['salesperson'] or 'N/A'} | "
            f"Current: {fmt_num(r['current_week'], 'GAL')} | "
            f"13Wk Avg: {fmt_num(r['avg_13wk'], 'GAL')} | "
            f"vs Avg: {fmt_pct(r['curr_ov_avg'])} | "
            f"WoW: {fmt_pct(r['wow_pct'])}"
        )
    lines.append(f"\nFUEL DECREASE ALERTS — MAIN ACCOUNTS (>=10,000 GAL avg, >=5,000 GAL current): {len(results['fuel_main_alerts'])} flagged")
    for a in results["fuel_main_alerts"][:50]:
        lines.append(
            f"  [{a['bucket']}] {a['customer']} | Region: {a['region']} | "
            f"Rep: {a['salesperson'] or 'N/A'} | Mgr: {a['area_manager'] or 'N/A'} | "
            f"This week: {fmt_num(a['current_week'], 'GAL')} | "
            f"Prior: {fmt_num(a['prior_week'], 'GAL')} | "
            f"Change: {fmt_pct(a['wow_pct'])} ({fmt_num(a['vol_change'], 'GAL')} vol)"
        )
    lines.append(f"\nFUEL DECREASE ALERTS — SECONDARY ACCOUNTS (<10,000 GAL avg): {len(results['fuel_secondary'])} flagged")
    for a in results["fuel_secondary"][:20]:
        lines.append(
            f"  [{a['bucket']}] {a['customer']} | Region: {a['region']} | "
            f"Rep: {a['salesperson'] or 'N/A'} | "
            f"WoW: {fmt_pct(a['wow_pct'])} | Vol: {fmt_num(a['vol_change'], 'GAL')}"
        )
    lines.append(f"\nNEWLY DARK ACCOUNTS (13wk avg >= 1,000 GAL, zero this period): {len(results['fuel_newly_dark'])} accounts")
    for a in results["fuel_newly_dark"]:
        lines.append(
            f"  {a['customer']} | Region: {a['region']} | "
            f"Rep: {a['salesperson'] or 'N/A'} | Mgr: {a['area_manager'] or 'N/A'} | "
            f"13Wk Avg: {fmt_num(a['avg_13wk'], 'GAL')} | "
            f"Last Known Vol: {fmt_num(a['last_known_vol'], 'GAL')}"
        )
    lines.append(f"\nFUEL INCREASES (sorted by volume gained): {len(results['fuel_increases'])} accounts")
    for a in results["fuel_increases"][:20]:
        wow_display = "N/A (returning from near-zero)" if a.get("suppress_pct") else fmt_pct(a['wow_pct'])
        lines.append(
            f"  {a['customer']} | Region: {a['region']} | "
            f"Rep: {a['salesperson'] or 'N/A'} | "
            f"This week: {fmt_num(a['current_week'], 'GAL')} | "
            f"Prior: {fmt_num(a['prior_week'], 'GAL')} | "
            f"WoW: {wow_display} | Vol gained: {fmt_num(a['vol_change'], 'GAL')}"
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
    prompt += """
 
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
Group by bucket: 20-30%, then 10-20%, then 0-10%.
### 20-30% Decrease
Table: Account | Region | Rep | Area Manager | This Week | Prior Week | WoW Change | Vol Change
### 10-20% Decrease
Same table format.
### 0-10% Decrease
Same table format.
After all buckets: 2-3 bullets noting rep or region concentration.
 
## 5. FUEL INCREASES
Table: Account | Region | Rep | This Week | Prior Week | WoW Change | Vol Gained
Sorted by absolute volume gained. If WoW reads "N/A (returning from near-zero)", display as "—".
After table: 2-3 bullets with top volume gainers.
 
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
- Decrease buckets: 0-10%, 10-20%, 20-30%. Accounts above 30% include in 20-30% bucket with a note.
- If a field shows N/A, omit it rather than displaying N/A
- If no accounts cross a threshold in a section, write "No alerts this period"
- Never fabricate data. Only report what is in the provided data.
"""
    return prompt
 
 
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
                    prompt = build_claude_prompt(results)
                    client = anthropic.Anthropic(
                        api_key=get_api_key(),
                        http_client=httpx.Client(verify=False)
                    )
                    message = client.messages.create(
                        model="claude-opus-4-6",
                        max_tokens=MAX_TOKENS,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    claude_output = message.content[0].text
 
                valid_regions = [r for r in results["region_summary"] if r["wow_pct"] is not None and r["current_week"] is not None and r["label"] and r["label"].startswith("Sales Region") and (r["current_week"] or 0) >= 1000000]
                regions_sorted = sorted(valid_regions, key=lambda x: x["wow_pct"], reverse=True)
                best_region = regions_sorted[0] if regions_sorted else None
                worst_region = regions_sorted[-1] if len(regions_sorted) > 1 else None
                group_labels = {"National", "East", "West"}
                group_regions = [r for r in results["region_summary"] if r["label"] in group_labels]
                national_volume = sum(r["current_week"] for r in group_regions if r["current_week"])
                national_prior = sum(r["prior_week"] for r in group_regions if r["prior_week"])
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
                        http_client=httpx.Client(verify=False)
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
            <div class="stat-card"><div class="stat-value">{nat_vol}</div><div class="stat-label">National Fuel Volume</div></div>
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
    st.markdown(analysis)
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
                        http_client=httpx.Client(verify=False)
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
 