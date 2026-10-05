from config import TTC_METRIC_SHEETS, TTC_METRIC_UNITS, TTC_MANAGER_DISPLAY


def ttc_fmt_num(val, unit=""):
    if val is None:
        return "N/A"
    if unit == "$":
        return f"${val:,.2f}"
    return f"{val:,.0f}{' ' + unit if unit else ''}"


def ttc_fmt_pct(val):
    if val is None:
        return "N/A"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.1f}%"


def ttc_md_table(headers, rows):
    if not rows:
        return "No notable movers this period."
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def build_ttc_prompt(manager, results):
    """manager: 'Brett Moody' | 'Keith Taggart' | 'TJ Atwood' | 'Overall (All Managers)'
    results: the dict returned by analyze_ttc_reports()"""
    is_overall = manager.startswith("Overall")
    managers_to_combine = ["Brett Moody", "Keith Taggart", "TJ Atwood"] if is_overall else [manager]
    display_name = "the entire Truck Care organization" if is_overall else TTC_MANAGER_DISPLAY.get(manager, manager)

    week_dates = results.get("week_dates", [])
    period_label = f"Week of {week_dates[0]}" if week_dates else "Unknown period"

    table_map = {}
    lines = []
    lines.append(f"TRUCK CARE WEEKLY REPORT — {display_name}")
    lines.append("=" * 60)

    for sheet in TTC_METRIC_SHEETS:
        unit = TTC_METRIC_UNITS.get(sheet, "")

        # ── Team rollup context (this week / avg / YoY / high-low) ──────────────
        if is_overall:
            this_week_total = 0
            avg_total = 0
            yoy_total = 0
            any_data = False
            for m in managers_to_combine:
                r = results["manager_rollups"].get(m, {}).get(sheet)
                if r:
                    any_data = True
                    this_week_total += r["this_week"] or 0
                    avg_total += r["avg_13wk"] or 0
                    yoy_total += r["yoy"] or 0
            if any_data:
                lines.append(
                    f"\n{sheet.upper()} — fleet-wide this week: {ttc_fmt_num(this_week_total, unit)} | "
                    f"13Wk Avg (sum of managers): {ttc_fmt_num(avg_total, unit)} | "
                    f"YOY (sum): {ttc_fmt_num(yoy_total, unit)}"
                )
        else:
            r = results["manager_rollups"].get(manager, {}).get(sheet)
            if r:
                lines.append(
                    f"\n{sheet.upper()} — this week: {ttc_fmt_num(r['this_week'], unit)} | "
                    f"13Wk Avg: {ttc_fmt_num(r['avg_13wk'], unit)} | "
                    f"vs Avg: {ttc_fmt_pct(r['curr_ov_avg'])} | "
                    f"YOY (vs same week last year): {ttc_fmt_num(r['yoy'], unit)} | "
                    f"13-Week HIGH: {ttc_fmt_num(r['high_val'], unit)} (week of {r['high_week']}) | "
                    f"13-Week LOW: {ttc_fmt_num(r['low_val'], unit)} (week of {r['low_week']})"
                )

        # ── Biggest swing this week (rep level) ──────────────────────────────────
        all_swings = []
        for m in managers_to_combine:
            all_swings.extend(results["manager_swings"].get(m, {}).get(sheet, []))
        all_swings.sort(key=lambda x: abs(x["delta"]), reverse=True)
        if all_swings:
            top = all_swings[0]
            lines.append(
                f"  BIGGEST SWING this week ({sheet}): {top['name']} "
                f"{ttc_fmt_num(top['delta'], unit)} (from {ttc_fmt_num(top['prior_week'], unit)} to {ttc_fmt_num(top['this_week'], unit)})"
            )

        # ── Rep breakdown pre-built table ────────────────────────────────────────
        rep_rows = [
            [s["name"], ttc_fmt_num(s["this_week"], unit), ttc_fmt_num(s["prior_week"], unit), ttc_fmt_num(s["delta"], unit), ttc_fmt_num(s.get("last_year"), unit)]
            for s in all_swings
        ]
        token = f"%%REP_TABLE_{sheet.upper().replace(' ', '_')}%%"
        table_map[token] = ttc_md_table(["Rep", "This Week", "Prior Week", "Change", "Last Year"], rep_rows)

        # ── Flagged customer movers pre-built table ──────────────────────────────
        all_flagged = []
        for m in managers_to_combine:
            all_flagged.extend(results["flagged_customers"].get(m, {}).get(sheet, []))
        all_flagged.sort(key=lambda x: abs(x["delta"]), reverse=True)
        cust_rows = [
            [c["customer"], c["rep"], ttc_fmt_num(c["this_week"], unit), ttc_fmt_num(c["prior_week"], unit), ttc_fmt_num(c["delta"], unit)]
            for c in all_flagged[:30]
        ]
        cust_token = f"%%CUSTOMER_TABLE_{sheet.upper().replace(' ', '_')}%%"
        table_map[cust_token] = ttc_md_table(["Customer", "Rep", "This Week", "Prior Week", "Change"], cust_rows)
        lines.append(f"  {len(all_flagged)} customer accounts flagged for notable {sheet} movement this period.")

    # ── Regional comparison (only for a single-manager view, not Overall) ──────────
    comparison_lines = []
    if not is_overall:
        all_managers_order = ["Brett Moody", "Keith Taggart", "TJ Atwood"]
        other_managers = [m for m in all_managers_order if m != manager]
        for sheet in TTC_METRIC_SHEETS:
            unit = TTC_METRIC_UNITS.get(sheet, "")
            parts = []
            for om in other_managers:
                r_other = results["manager_rollups"].get(om, {}).get(sheet)
                if r_other:
                    parts.append(
                        f"{TTC_MANAGER_DISPLAY.get(om, om)}: this week {ttc_fmt_num(r_other['this_week'], unit)}, "
                        f"vs 13Wk Avg {ttc_fmt_pct(r_other['curr_ov_avg'])}"
                    )
            if parts:
                comparison_lines.append(f"  {sheet}: " + " | ".join(parts))
        if comparison_lines:
            lines.append("\nCOMPARISON DATA -- the other two managers' same-week figures, for context only (do not build a table, write 2-3 prose sentences instead):")
            lines.extend(comparison_lines)

    # ── Monthly (optional) ───────────────────────────────────────────────────────
    monthly_available = results.get("monthly") is not None
    if monthly_available:
        monthly = results["monthly"]
        period = monthly.get("period", "Unknown period")
        if is_overall:
            profit = sum((monthly["by_manager"].get(m, {}).get("profit_all_in") or 0) for m in managers_to_combine)
            tire_qty = sum((monthly["by_manager"].get(m, {}).get("tire_qty") or 0) for m in managers_to_combine)
            retread_qty = sum((monthly["by_manager"].get(m, {}).get("retread_qty") or 0) for m in managers_to_combine)
            yoy_tires = sum((monthly["by_manager"].get(m, {}).get("yoy_tires_retreads") or 0) for m in managers_to_combine)
            ppg = None
        else:
            md = monthly["by_manager"].get(manager, {})
            profit = md.get("profit_all_in")
            tire_qty = md.get("tire_qty")
            retread_qty = md.get("retread_qty")
            yoy_tires = md.get("yoy_tires_retreads")
            ppg = md.get("ppg_all_in")
        lines.append(f"\nMONTHLY DATA — Period: {period} (from the separately-uploaded Monthly Sales Report, NOT this week's data -- label it with this period explicitly, never imply it is current-week):")
        lines.append(f"  Profit [All-In]: {ttc_fmt_num(profit, '$')}")
        if ppg is not None:
            lines.append(f"  PPG [All-In]: {ttc_fmt_num(ppg)}")
        lines.append(f"  New Tire Quantity: {ttc_fmt_num(tire_qty, 'EA')} | Retread Quantity: {ttc_fmt_num(retread_qty, 'EA')}")
        lines.append(f"  YOY Tires & Retreads (monthly): {ttc_fmt_num(yoy_tires, 'EA')}")

    prompt = "\n".join(lines)

    comparison_section_instruction = (
        "Using the COMPARISON DATA given above, write 2-3 sentences comparing this manager's movement this week "
        "to the other two managers, for whichever metrics show the most notable difference or similarity. "
        "State plainly whether a trend is isolated to this manager's territory or showing up broadly across other regions too "
        "(e.g. 'Compared to East and National accounts, West's tire decline looks isolated -- both other regions are tracking near their 13-week average.'). "
        "Do not build a table here, this is prose only."
        if (not is_overall and comparison_lines) else
        "This is the combined view across all three managers, so a regional comparison does not apply here -- skip this section "
        "with a single sentence noting that, or omit it entirely."
    )

    monthly_section_instruction = (
        "Insert one short subsection using the MONTHLY DATA given above -- Profit [All-In], PPG if given, "
        "and the new-vs-retread tire split. Label it clearly with the Monthly file's own period (e.g. 'As of August 2026') "
        "so it is never confused with this week's figures. There is no 'Used Tire' figure anywhere in the data -- "
        "do not invent one or mention a three-way split."
        if monthly_available else
        "No Monthly file was uploaded this period. Write one sentence noting that Profit/PPG and the tire-type split "
        "are not available without it, and move on -- do not fabricate or estimate these figures from weekly data."
    )

    rep_table_tokens = "\n".join(
        f"#### {sheet}\nOn its own line, output exactly: %%REP_TABLE_{sheet.upper().replace(' ', '_')}%%"
        for sheet in TTC_METRIC_SHEETS
    )
    customer_table_tokens = "\n".join(
        f"#### {sheet}\nOn its own line, output exactly: %%CUSTOMER_TABLE_{sheet.upper().replace(' ', '_')}%%"
        for sheet in TTC_METRIC_SHEETS
    )

    prompt += f"""

---
INSTRUCTIONS:
You are the Truck Care Intelligence Agent for Love's Travel Stops, writing for {display_name}. This report replaces a plain week-over-week report that leadership doesn't trust, because a single heavy week skews the WoW story -- so lean on the 13-week high/low context and unit counts, not raw percentages, wherever possible.

ABSOLUTE RULE ON TABLES: every place a table belongs, output ONLY the exact placeholder token given (format %%SOMETHING%%) on its own line, nothing else on that line. It will be swapped for the real table after you respond. Do not build your own table, add columns, or compute anything the token's table doesn't already show.

ABSOLUTE RULE ON THE DATE: the Period Ending line is already filled in for you above as literal text -- "{period_label}". Copy it exactly. Do not guess, infer, or substitute a different date from anywhere else in this data, even if another date appears more prominently elsewhere in the tables.

TONE AND STYLE:
- Write as a senior analyst. Direct, confident, factual.
- Call out swings and totals in UNIT COUNTS (EA, Hrs, $), not percentages -- this is an explicit, stated preference from the audience.
- Never tell leadership what to do. Surface the data, let them draw conclusions.
- Never use backticks or code formatting anywhere, for any reason.
- Numbers must always include units.

OUTPUT FORMAT:

## TRUCK CARE WEEKLY BRIEF — {display_name.upper()}
**Period Ending: {period_label}**

## 1. OPENING
2-3 bullets: total units this week vs. 13-week avg vs. same week last year, for each of the four metrics (Tires, PM, TCE Spend per Truck, Labor Hrs). Use the exact figures given above -- do not recompute.

## 2. REGIONAL COMPARISON
{comparison_section_instruction}

## 3. THIS WEEK'S STORY
1-2 bullets on the single biggest swing(s) called out above, in unit counts. Name the rep and the account context if relevant.

## 4. WEEKLY HIGHS AND LOWS (13-WEEK WINDOW)
For each metric, one bullet stating the 13-week high and low (value and week), and where this week sits relative to both. This is the section that replaces the misleading single-week WoW framing -- make clear whether this week is near a recent high, a recent low, or mid-range.

## 5. MONTHLY VIEW
{monthly_section_instruction}

## 6. REP BREAKDOWN
{rep_table_tokens}
After all four tables: 2-3 bullets noting which reps are moving most, in either direction.

## 7. NOTABLE CUSTOMER ACCOUNTS
{customer_table_tokens}
After all four tables: 2-3 bullets on the customers driving the biggest movement this period.

## 8. CLOSING TAKEAWAYS
2-3 bullets. Each names a specific rep or customer, states a specific unit-count number, surfaces an observation worth remembering.

DATA CONTEXT:
- All figures are in unit counts (EA for Tires/PM, Hrs for Labor, $ for TCE Spend per Truck) unless a percentage is explicitly requested.
- Never fabricate data. Only use what is given above.
"""
    return prompt, table_map
