import os
import tempfile
import anthropic
import httpx
from flask import Blueprint, render_template, request, jsonify
from app.analyzer import analyze_reports
from app.monthly_analyzer import analyze_monthly_report
from config import ANTHROPIC_API_KEY, METRIC_UNITS, MAX_TOKENS
 
bp = Blueprint("main", __name__)
 
 
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
- Minimize bold formatting. Use bold only for section headers (which are already formatted), never for account names, rep names, metrics, or numbers in the text.
 
OUTPUT FORMAT -- follow this exact order with no extra spacing between sections:
 
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
The This Week column should show 0 GAL for every row to emphasize the drop to zero. Do not characterize the Last Known Volume as a trend, upswing, or decline - it is a single week's figure and may be an outlier. State it plainly.
After table: 2-3 bullets noting patterns in regions or reps with multiple dark accounts, and any concentration of volume loss.
 
## 4. FUEL DECREASE ALERTS
Group by bucket in this order: 20-30%, then 10-20%, then 0-10%.
Within each bucket, list accounts sorted by absolute volume lost, largest loss at the top.
### 20-30% Decrease
Table: Account | Region | Rep | Area Manager | This Week | Prior Week | WoW Change | Vol Change
### 10-20% Decrease
Same table format.
### 0-10% Decrease
Same table format.
After all buckets: 2-3 bullets noting rep or region concentration, and any single account that stands out by volume magnitude.
 
## 5. FUEL INCREASES
Table: Account | Region | Rep | This Week | Prior Week | WoW Change | Vol Gained
Sorted by absolute volume gained, largest at top. If a WoW value reads "N/A (returning from near-zero)", display it as "—" in the table and do not describe that account's percentage change in any surrounding text -- only reference its volume gained.
After table: 2-3 bullets with the top volume gainers and any regional or rep concentration.
 
## 6. NON-FUEL HIGHLIGHTS
For each metric (Tires, PM, TCE Spend per Truck, Labor Hours), provide 2-3 bullets covering the steepest decreases and increases. Only significant movers. No prose paragraphs.

## 7. KEY TAKEAWAYS
3 bullets. Each names a specific account or rep, states a specific number, and surfaces an observation -- not a directive.
 
## 8. CLOSING
One sentence. Do not make absolute claims such as "all regions" unless every single region meets the condition. State the closing factually based only on the data shown.
 
DATA CONTEXT:
- Main accounts: 13-week average >= 10,000 GAL and current week >= 5,000 GAL
- Secondary accounts: below those thresholds -- surface separately, do not mix
- Newly dark: accounts with 13-week avg >= 1,000 GAL reporting zero this period
- Decrease buckets: 0-10%, 10-20%, 20-30%. Accounts above 30% include in the 20-30% bucket with a note.
- If a field shows N/A, omit it from the output rather than displaying N/A
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
    lines.append("(An account appears here only if it declined every month across this window AND started the window at or above 25,000 GAL.)")
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
- Present information as observations and insights -- not directives or prescriptions.
- Never tell leadership what to do or how to respond. Surface the data and let them draw conclusions.
- Never call out gaps, failures, or accountability issues. State facts neutrally.
- Never write: "it is worth noting", "as we can see", "it appears that", "please note", "requires immediate action", "should follow up", "accountability gap"
- State declines plainly: "down 9.1% year-over-year"
- Numbers must always include units (GAL, $, EA, Hrs)
- Keep sections tight -- no extra blank lines between sections, no padding
- Minimize bold formatting. Use bold only for section headers (which are already formatted), never for account names, rep names, metrics, or numbers in the text.
 
OUTPUT FORMAT -- follow this exact order with no extra spacing between sections:
 
## MONTHLY FLEET SALES BRIEF
**Period: {period}**
 
## 1. OPENING
## 1. OPENING
2-3 bullets. Total fleet hierarchy volume and its year-over-year direction. Overall profit picture. The single clearest field group headline. Note: National, East, and West are the three field reporting groups — do not imply one is a subset of another or that "National" means company-wide total.
 
## 2. REGIONAL PERFORMANCE
### Top 3 Regions by Year-over-Year Growth
Table: Rank | Region | Rep | DSL Volume | YOY | Profit | PPG
After table: 2-3 bullets with context on what's driving each region's YOY performance.
 
### Bottom 3 Regions by Year-over-Year Change
Same table format.
After table: 2-3 bullets with context on which factors are weighing on each region.
 
## 3. AREA MANAGER PERFORMANCE
Table: Rank | Area Manager | Group | DSL Volume | YOY
After table: 2-3 bullets covering the top managers by volume and any with notable YOY movement (positive or negative).
 
## 4. MULTI-MONTH TREND
Table: Account | Region | 4 Months Ago | Most Recent Month | Decline % | Volume Lost
This table reflects only the recent {window}-month window ({month_str}) and is not a full-year view. Accounts appear only if they declined every month in this window starting at or above 25,000 GAL.
After table: 2-3 bullets noting the largest absolute declines and any region or rep concentration in the declining accounts.
 
## 5. PROFIT & MARGIN
2-3 bullets. Highest and lowest profit regions, any notable price-per-gallon spread across regions. Factual observations only.
 
## 6. KEY TAKEAWAYS
3 bullets. Each names a specific region, account, or area manager, states a specific number, and surfaces an observation -- not a directive.
 
## 7. CLOSING
One sentence. Do not make absolute claims such as "all regions" unless every single region meets the condition. State the closing factually based only on the data shown.
 
DATA CONTEXT:
- This is monthly data. YOY in this report is reliable and reconstructs correctly -- use it confidently.
- The multi-month trend reflects ONLY the recent {window}-month window and only accounts that declined every month in that window starting at or above 25,000 GAL. Always frame it as a recent-window trend, never as a full-year or all-time decline.
- PPG is price/profit per gallon in dollars. Profit is in dollars.
- If a field shows N/A, omit it rather than displaying N/A.
- Never fabricate data. Only report what is in the provided data.
"""
    return prompt
 
 
@bp.route("/")
def index():
    return render_template("index.html")
 
 
@bp.route("/analyze", methods=["POST"])
def analyze():
    mode = request.form.get("mode", "weekly")
 
    client = anthropic.Anthropic(
        api_key=ANTHROPIC_API_KEY,
        http_client=httpx.Client(verify=False)
    )
 
    # ── MONTHLY MODE ─────────────────────────────────────────
    if mode == "monthly":
        monthly_file = request.files.get("monthly_report")
        if not monthly_file or monthly_file.filename == "":
            return jsonify({"error": "Please upload the Monthly Sales Report."}), 400
 
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as mf:
            monthly_file.save(mf.name)
            monthly_path = mf.name
 
        try:
            results = analyze_monthly_report(monthly_path)
            prompt = build_monthly_prompt(results)
 
            message = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}]
            )
            claude_output = message.content[0].text
 
            summary = {
                "report_date": results["period"],
                "region_count": len(results["regional"]),
                "manager_count": len(results["area_managers"]),
                "declining_count": len(results["trend_declining"]),
                "trend_window": results["trend_window"],
                "errors": results["errors"],
            }
 
            return jsonify({
                "success": True,
                "mode": "monthly",
                "summary": summary,
                "analysis": claude_output,
                "raw_results": {
                    "regional": results["regional"][:40],
                    "area_managers": results["area_managers"][:25],
                    "trend_declining": results["trend_declining"][:30],
                    "trend_months": results["trend_months"],
                }
            })
 
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Analysis failed: {str(e)}"}), 500
 
        finally:
            try:
                os.unlink(monthly_path)
            except Exception:
                pass
 
    # ── WEEKLY MODE (default) ────────────────────────────────
    if "customer_report" not in request.files and "region_report" not in request.files:
        return jsonify({"error": "Please upload at least one report file."}), 400
 
    customer_file = request.files.get("customer_report")
    region_file = request.files.get("region_report")
 
    customer_path = None
    region_path = None
 
    if customer_file and customer_file.filename != "":
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as cf:
            customer_file.save(cf.name)
            customer_path = cf.name
 
    if region_file and region_file.filename != "":
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as rf:
            region_file.save(rf.name)
            region_path = rf.name
 
    try:
        results = analyze_reports(customer_path, region_path)
        prompt = build_claude_prompt(results)
 
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

        summary = {
            "report_date": results["report_date"],
            "best_region_name": best_region.get("label", "N/A") if best_region else "N/A",
            "best_region_wow": best_region.get("wow_pct", 0) if best_region else 0,
            "worst_region_name": worst_region.get("label", "N/A") if worst_region else "N/A",
            "worst_region_wow": worst_region.get("wow_pct", 0) if worst_region else 0,
            "national_volume": national_volume,
            "national_wow": national_wow,
            "region_count": len(results["region_summary"]),
            "newly_dark_count": len(results["fuel_newly_dark"]),
            "errors": results["errors"],
        }
        return jsonify({
            "success": True,
            "mode": "weekly",
            "summary": summary,
            "analysis": claude_output,
            "raw_results": {
                "fuel_main_alerts": results["fuel_main_alerts"][:20],
                "fuel_newly_dark": results["fuel_newly_dark"],
                "region_summary": results["region_summary"][:20],
            }
        })
 
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500
 
    finally:
        try:
            if customer_path:
                os.unlink(customer_path)
            if region_path:
                os.unlink(region_path)
        except Exception:
            pass
@bp.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    question = data.get("question", "")
    context = data.get("context", "")

    if not question or not context:
        return jsonify({"error": "Missing question or context"}), 400

    client = anthropic.Anthropic(
        api_key=ANTHROPIC_API_KEY,
        http_client=httpx.Client(verify=False)
    )

    try:
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"""You are the Fleet Sales Intelligence Agent for Love's Travel Stops. A user has already run an analysis and is now asking a follow-up question about the results.

ANALYSIS CONTEXT:
{context}

USER QUESTION:
{question}

Answer concisely and factually based only on the data provided. Use specific numbers. Do not fabricate data."""
            }]
        )
        return jsonify({"answer": message.content[0].text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500