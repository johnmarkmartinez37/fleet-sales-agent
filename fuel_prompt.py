from config import METRIC_UNITS, INSIDE_SALES_REGIONS
from alignment import region_key


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


def is_inside_sales(region, inside_regions=None):
    codes = inside_regions if inside_regions is not None else INSIDE_SALES_REGIONS
    return region_key(region) in codes


def gal_tier(vol_change):
    abs_vol = abs(vol_change)
    if abs_vol >= 1500:
        return "Tier 1 (1,500+ GAL Lost)"
    elif abs_vol >= 500:
        return "Tier 2 (500-1,499 GAL Lost)"
    elif abs_vol >= 100:
        return "Tier 3 (100-499 GAL Lost)"
    return None


def md_table(headers, rows):
    if not rows:
        return "No alerts this period."
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


# ── Weekly fuel prompt ──────────────────────────────────────────────────────────
def build_claude_prompt(results, email_mode=False, region_label=None, inside_regions=None):
    """Build the weekly fuel prompt.

    email_mode=True  -> prompt for a single-region email: no Area Manager column in the tables
                        (the Area Manager is CC'd on the email instead).
    region_label     -> e.g. "Region 16"; used in the brief's title in email mode.
    inside_regions   -> optional set of region numbers treated as Inside Sales (defaults to config).

    If no Region report data is present (customer-only upload), the brief has no fleet-wide total
    and no Top/Bottom 3 Regions section, and sections are renumbered.
    """
    date = results.get("report_date", "Unknown")
    show_am = not email_mode
    lines = []
    lines.append(f"FLEET SALES REPORT — Period Ending {date}")
    lines.append("=" * 60)

    table_map = {}

    fleet_total_row = next((r for r in results["region_summary"] if r["label"] == "Fleet Hierarchy"), None)
    fleet_total_line = ""
    if fleet_total_row and fleet_total_row["current_week"]:
        fleet_total_line = f"FLEET-WIDE TOTAL FUEL VOLUME (use this exact figure for any total-fleet-volume statement, do not recompute): {fmt_num(fleet_total_row['current_week'], 'GAL')}, WoW: {fmt_pct(fleet_total_row['wow_pct'])}"

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
    customer_only = (not has_region_data) and (not fleet_total_line)

    if customer_only:
        lines.append("\nSCOPE: this brief is built from account-level customer data only. No fleet-wide, national, or regional total volumes exist in this data.")
    else:
        lines.append(f"\n{fleet_total_line}" if fleet_total_line else "\nFLEET-WIDE TOTAL: not available (no Region report data for this figure).")

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
    elif not customer_only:
        lines.append("\nNo region-level totals were provided in the source data this period (customer-only upload) -- there is no Top 3 / Bottom 3 regional table this period.")

    def inside(a):
        return is_inside_sales(a["region"], inside_regions)

    regular_main = [a for a in results["fuel_main_alerts"] if not inside(a)]
    inside_main = [a for a in results["fuel_main_alerts"] if inside(a)]
    regular_secondary = [a for a in results["fuel_secondary"] if not inside(a)]
    inside_secondary = [a for a in results["fuel_secondary"] if inside(a)]

    all_accounts_for_scope = (
        results["fuel_main_alerts"] + results["fuel_secondary"]
        + results["fuel_increases"] + results["fuel_newly_dark"]
    )
    has_regular = any(not inside(a) for a in all_accounts_for_scope)
    has_inside = any(inside(a) for a in all_accounts_for_scope)

    dec_headers = ["Account", "Region", "Rep"] + (["Area Manager"] if show_am else []) + ["This Week", "Prior Week", "WoW Change", "Vol Change"]

    def dec_row(a):
        row = [a["customer"], a["region"], a["salesperson"] or "N/A"]
        if show_am:
            row.append(a["area_manager"] or "N/A")
        row += [fmt_num(a["current_week"], "GAL"), fmt_num(a["prior_week"], "GAL"),
                fmt_pct(a["wow_pct"]), fmt_num(a["vol_change"], "GAL")]
        return row

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
        inside_dec_headers = ["Account", "Region", "Rep"] + (["Area Manager"] if show_am else []) + ["This Week", "Prior Week", "Vol Change"]

        def inside_dec_row(a):
            row = [a["customer"], a["region"], a["salesperson"] or "N/A"]
            if show_am:
                row.append(a["area_manager"] or "N/A")
            row += [fmt_num(a["current_week"], "GAL"), fmt_num(a["prior_week"], "GAL"), fmt_num(a["vol_change"], "GAL")]
            return row

        table_map["%%INS_DEC_T1%%"] = md_table(inside_dec_headers, [inside_dec_row(a) for a in t1])
        table_map["%%INS_DEC_T2%%"] = md_table(inside_dec_headers, [inside_dec_row(a) for a in t2])
        table_map["%%INS_DEC_T3%%"] = md_table(inside_dec_headers, [inside_dec_row(a) for a in t3])
        lines.append(f"\nFor context only: {len(t1)} Inside Sales accounts in Tier 1, {len(t2)} in Tier 2, {len(t3)} in Tier 3.")

    dark_headers = ["Account", "Region", "Rep"] + (["Area Manager"] if show_am else []) + ["13Wk Avg", "This Week", "Last Known Volume"]

    def dark_row(a):
        row = [a["customer"], a["region"], a["salesperson"] or "N/A"]
        if show_am:
            row.append(a["area_manager"] or "N/A")
        row += [fmt_num(a["avg_13wk"], "GAL"), "0 GAL", fmt_num(a["last_known_vol"], "GAL")]
        return row

    table_map["%%DARK_TABLE%%"] = md_table(dark_headers, [dark_row(a) for a in results["fuel_newly_dark"]])
    lines.append(f"\nFor context only: {len(results['fuel_newly_dark'])} newly dark accounts this period.")
    for a in results["fuel_newly_dark"]:
        lines.append(f"  DARK: {a['customer']} | Region: {a['region']} | Rep: {a['salesperson'] or 'N/A'} | 13Wk Avg: {fmt_num(a['avg_13wk'], 'GAL')} | Last Known: {fmt_num(a['last_known_vol'], 'GAL')}")

    regular_increases = sorted([a for a in results["fuel_increases"] if not inside(a)], key=lambda x: x["vol_change"], reverse=True)
    inside_increases = sorted([a for a in results["fuel_increases"] if inside(a)], key=lambda x: x["vol_change"], reverse=True)

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

    # ── Sections (numbered dynamically so a dropped section never leaves a gap) ──
    if customer_only:
        opening_body = (
            "2-3 bullet points based ONLY on the account-level data above: how many accounts are in each decrease band, "
            "how many went newly dark, how many increased, and the single largest mover. "
            "Do not state, estimate, or imply any fleet-wide, national, or regional total volume -- none is provided."
        )
    else:
        opening_body = "2-3 bullet points. Total fuel volume vs. rolling average (use the FLEET-WIDE TOTAL figure given above verbatim, do not recompute it). Standout regional trend. National performance direction."

    sections = [("OPENING", opening_body)]
    if not customer_only:
        sections.append((
            "REGIONAL HIGHLIGHTS",
            f"### Top 3 Performing Regions\n{top3_instruction}\nAfter (table token or sentences): 2-3 bullets with context on what's driving each region's performance.\n\n"
            f"### Bottom 3 Underperforming Regions\n{bottom3_instruction}\nAfter (table token or bullets): 2-3 bullets with context on which accounts are driving underperformance in each region."
        ))
    sections.append(("NEWLY DARK ACCOUNTS", "On its own line, output exactly: %%DARK_TABLE%%\nAfter table token: 2-3 bullets noting patterns in regions or reps with multiple dark accounts."))
    sections.append(("FUEL DECREASE ALERTS", f"{section_4_scope}\n{section_4_headings}\nAfter all table tokens above: 2-3 bullets noting rep or region concentration."))
    sections.append(("FUEL INCREASES", f"{section_5_headings}\nAfter table token(s): 2-3 bullets with top volume gainers."))
    sections.append(("NON-FUEL HIGHLIGHTS", "For each metric (Tires, PM, TCE Spend per Truck, Labor Hours), 2-3 bullets covering steepest movers. Write all numbers as plain text, no backticks, no code formatting, single $ sign for dollar amounts (e.g. $1,750.00)."))
    sections.append(("KEY TAKEAWAYS", "3 bullets. Each names a specific account or rep, states a specific number, surfaces an observation."))
    sections.append(("CLOSING", "One sentence. Factual only."))

    output_format = "\n\n".join(f"## {i}. {title}\n{body}" for i, (title, body) in enumerate(sections, start=1))

    title_line = "## FLEET SALES INTELLIGENCE BRIEF"
    if email_mode and region_label:
        title_line += f" — {region_label.upper()}"

    am_tone_line = "- Reference area manager alongside salesperson when available\n" if show_am else ""
    email_note = (
        "\nEMAIL NOTE: this brief is delivered by email to the sales rep for this region only. "
        "Do not mention area managers, and do not compare this region to other regions or to any fleet-wide total.\n"
        if email_mode else ""
    )

    prompt += f"""

---
INSTRUCTIONS:
You are the Fleet Sales Intelligence Agent for Love's Travel Stops fleet sales team. Generate a professional executive insight summary for SVP-level leadership.
{email_note}
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
{am_tone_line}- Keep sections tight -- no extra blank lines between sections, no padding
- Minimize bold formatting. Use bold only for section headers, never for account names, rep names, metrics, or numbers in the text.
- Never use backticks or code formatting anywhere in your response, for any reason, under any circumstances.

OUTPUT FORMAT -- follow this exact order:

{title_line}
**Period Ending: {date}**

{output_format}

DATA CONTEXT:
- Main accounts: 13-week average >= 10,000 GAL and current week >= 5,000 GAL
- Secondary accounts: below those thresholds
- Newly dark: accounts with 13-week avg >= 1,000 GAL reporting zero this period
- Accounts moving more than 30% in either direction are intentionally excluded -- those are covered by a separate fleet exception report.
- Never fabricate data.
"""
    return prompt, table_map
