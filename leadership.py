"""Leadership emails: the executive summary, the East / West VP summaries and the combined Inside Sales (Inside East + Inside West) brief.

Every number and every table is computed here in Python from the 13-week customer report. Claude is only
asked to write short commentary around bare %%TOKEN%% placeholders, exactly like the rep briefs.

No Streamlit dependency.
"""
import re

import openpyxl

from alignment import region_key, first_name, make_email, is_open_seat
from analyzer import safe_float, clean_field, find_last_known_value, NEWLY_DARK_MIN_GAL
from config import (
    CUSTOMER_COLS, CUSTOMER_DATA_START_ROW, FUEL_SHEET,
    TTC_METRIC_SHEETS, TTC_METRIC_UNITS, TTC_KNOWN_MANAGERS, TTC_EMAIL_LABELS, TTC_INSIDE_LABEL,
    EXEC_RECIPIENTS, EXEC_SUBJECT_LABEL, MANAGER_BRIEFS, GROUP_MERGES, VP_BRIEFS,
    REGION_DATA_START_ROW, REGION_ROLLUPS,
    LEADERSHIP_TOP_N, MANAGER_TOP_N, EXEC_EXCLUDE_30PCT_MOVES, EXEC_TTC_EXCLUDE_30PCT_MOVES, EXEC_LIST_EXCLUDED_REGIONS,
)
from fuel_prompt import md_table

INCREASE_MIN_GAL = 5000          # same floor the rep briefs use to call an account an "increase" (for the dark-account de-dupe)
NOT_ALIGNED = "Not in alignment file"


# ═══════════════════════════════════════════════════════════════════════════════
# Formatting
# ═══════════════════════════════════════════════════════════════════════════════
def fmt_signed(val, unit=""):
    """+1,234 GAL / -1,234 GAL / $+12.50 style; N/A when missing."""
    if val is None:
        return "N/A"
    if unit == "$":
        return f"+${val:,.2f}" if val > 0 else (f"-${abs(val):,.2f}" if val < 0 else "$0.00")
    sign = "+" if val > 0 else ("-" if val < 0 else "")
    rounded = round(abs(val))
    if rounded == 0:
        sign = ""
    return f"{sign}{rounded:,.0f}{' ' + unit if unit else ''}"


def fmt_plain(val, unit=""):
    if val is None:
        return "N/A"
    if unit == "$":
        return f"${val:,.2f}"
    return f"{val:,.0f}{' ' + unit if unit else ''}"


def pct(change, base):
    """change / base as a signed % string; N/A when the base isn't positive."""
    if change is None or base is None or base <= 0:
        return "N/A"
    v = change / base * 100
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.1f}%"


def _add(a, b):
    """None-aware sum: None only when both are None."""
    if a is None:
        return b
    if b is None:
        return a
    return a + b


# ═══════════════════════════════════════════════════════════════════════════════
# Reading the fuel customer report (every row -- the rep briefs only keep flagged accounts)
# ═══════════════════════════════════════════════════════════════════════════════
def read_fuel_rows(customer_path):
    """Every customer row on the Fuel tab, with the YoY columns the rep briefs don't use."""
    C = CUSTOMER_COLS
    wb = openpyxl.load_workbook(customer_path, data_only=True)
    if FUEL_SHEET not in wb.sheetnames:
        raise ValueError(f"The customer report has no '{FUEL_SHEET}' tab.")
    rows = []
    for i, row in enumerate(wb[FUEL_SHEET].iter_rows(values_only=True)):
        if i < CUSTOMER_DATA_START_ROW:
            continue
        customer = clean_field(row[C["customer"]]) if len(row) > C["customer"] else None
        if not customer or customer == "Customer":
            continue

        def col(name):
            idx = C[name]
            return safe_float(row[idx]) if idx < len(row) else None

        rows.append({
            "region": REGION_ROLLUPS.get(region_key(clean_field(row[C["region"]])), region_key(clean_field(row[C["region"]]))),
            "customer": customer,
            "rep": clean_field(row[C["salesperson"]]),
            "avg_13wk": col("avg_13wk"),
            "current": col("current_week"),
            "prior": col("prior_week"),
            "yoy_week": col("yoy_cur_week"),       # column H: this week minus the same week last year (GAL)
            "yoy_avg_chg": col("yoy_dsl_avg"),     # column W: 13-week avg minus last year's 13-week avg (GAL)
            "last_known": find_last_known_value(row, C["current_week"], C["yoy_avg"]),
        })
    return rows


def aggregate_accounts(rows):
    """One record per (region, customer). A few customers are listed on several lines in the same region;
    those lines are one account, so their gallons are added together."""
    accts = {}
    for r in rows:
        key = (r["region"], r["customer"])
        a = accts.get(key)
        if a is None:
            accts[key] = dict(r)
            continue
        for f in ("avg_13wk", "current", "prior", "yoy_week", "yoy_avg_chg", "last_known"):
            a[f] = _add(a[f], r[f])
        if not a["rep"] and r["rep"]:
            a["rep"] = r["rep"]
    return list(accts.values())


def totals(accts):
    """Roll a set of accounts up to one summary dict (None-safe)."""
    cur = sum(a["current"] or 0 for a in accts)
    pri = sum(a["prior"] or 0 for a in accts)
    avg = sum(a["avg_13wk"] or 0 for a in accts)
    yoy = sum(a["yoy_week"] or 0 for a in accts)
    yoy_avg = sum(a["yoy_avg_chg"] or 0 for a in accts)
    return {
        "current": cur, "prior": pri, "avg": avg,
        "yoy": yoy, "ly": cur - yoy,
        "wow": cur - pri,
        "vs_avg": cur - avg,
        "avg_yoy": yoy_avg, "ly_avg": avg - yoy_avg,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Fleet Region report (the 'Graphs' report the executives use on the weekly sales call)
# ═══════════════════════════════════════════════════════════════════════════════
REGION_REPORT_SHEETS = ["Fuel", "Tires", "PM", "TCE Spend per Truck", "Labor Hrs"]


def _region_row(row):
    def col(i):
        return safe_float(row[i]) if len(row) > i else None
    return {
        "label": clean_field(row[0]), "rep": clean_field(row[1]) if len(row) > 1 else None,
        "avg": col(3), "vs_avg_pct": col(4), "yoy": col(5), "current": col(6), "prior": col(7),
        "yoy_dsl_avg": col(20),
    }


def read_region_report(path):
    """Fleet / group / region rows from the fleet Region report. These are the numbers on the executives' graphs,
    so the leadership emails use them for every fleet, group and region total."""
    wb = openpyxl.load_workbook(path, data_only=True)
    if "Fuel" not in wb.sheetnames:
        raise ValueError("The fleet Region report has no 'Fuel' tab.")
    out = {"date": None, "fleet": {}, "groups": {}, "regions": {}}
    for sheet in REGION_REPORT_SHEETS:
        if sheet not in wb.sheetnames:
            continue
        rows = list(wb[sheet].iter_rows(values_only=True))
        if sheet == "Fuel" and len(rows) > 2 and rows[2] and len(rows[2]) > 1 and rows[2][1]:
            out["date"] = str(rows[2][1]).strip()
        for row in rows[REGION_DATA_START_ROW:]:
            label = clean_field(row[0]) if row else None
            if not label:
                continue
            if label == "Fleet Hierarchy" and sheet not in out["fleet"]:
                out["fleet"][sheet] = _region_row(row)
            elif sheet == "Fuel":
                rep = clean_field(row[1]) if len(row) > 1 else None
                m = re.fullmatch(r"Sales Region\s+(\d+)", label)
                if rep == "Reporting Group":
                    out["groups"][label] = _region_row(row)
                elif m:
                    out["regions"][m.group(1).lstrip("0") or "0"] = _region_row(row)
    if "Fuel" not in out["fleet"]:
        raise ValueError("This doesn't look like the fleet Region report: there is no 'Fleet Hierarchy' row on its Fuel tab.")
    return out


def totals_from_row(r):
    """Same shape as totals(), taken straight from a Region report row. Every figure is rounded to whole gallons first and
    the changes are taken from those rounded figures, so each table row adds up exactly as printed."""
    cur_raw, pri_raw, avg_raw = r["current"] or 0, r["prior"] or 0, r["avg"] or 0
    yoy_raw, yoy_avg_raw = r["yoy"] or 0, r["yoy_dsl_avg"] or 0
    cur, pri, avg = round(cur_raw), round(pri_raw), round(avg_raw)
    ly, ly_avg = round(cur_raw - yoy_raw), round(avg_raw - yoy_avg_raw)
    return {"current": cur, "prior": pri, "avg": avg, "yoy": cur - ly, "ly": ly, "wow": cur - pri,
            "vs_avg": cur - avg, "avg_yoy": avg - ly_avg, "ly_avg": ly_avg}


def _merged_name(g):
    for new, members in GROUP_MERGES.items():
        if g in members:
            return new
    return g


def merge_region_rows(rows, label):
    """Add several Region report rows (e.g. Inside East + Inside West) into one row."""
    def s(k):
        vals = [r[k] for r in rows if r.get(k) is not None]
        return sum(vals) if vals else None
    return {"label": label, "rep": None, "avg": s("avg"), "vs_avg_pct": None, "yoy": s("yoy"),
            "current": s("current"), "prior": s("prior"), "yoy_dsl_avg": s("yoy_dsl_avg")}


def merged_groups(rr):
    """Group rows of the Region report, with GROUP_MERGES applied (Inside East + Inside West -> Inside Sales)."""
    by = {}
    for g, r in rr["groups"].items():
        by.setdefault(_merged_name(g), []).append(r)
    return {name: (rows[0] if len(rows) == 1 and name == rows[0]["label"] else merge_region_rows(rows, name))
            for name, rows in by.items()}


GROUP_HEADERS = ["Group", "This Week", "WoW Change (GAL)", "WoW %", "vs 13Wk Avg %",
                 "YoY vs Same Wk LY (GAL)", "YoY vs Same Wk LY %", "13Wk Avg YoY (GAL)", "13Wk Avg YoY %"]


def group_row(label, t):
    return [label, fmt_plain(t["current"], "GAL"), fmt_signed(t["wow"], "GAL"), pct(t["wow"], t["prior"]),
            pct(t["vs_avg"], t["avg"]), fmt_signed(t["yoy"], "GAL"), pct(t["yoy"], t["ly"]),
            fmt_signed(t["avg_yoy"], "GAL"), pct(t["avg_yoy"], t["ly_avg"])]


def group_table_from_region(rr):
    rows = [group_row(g, totals_from_row(r)) for g, r in merged_groups(rr).items()]
    rows.append(group_row("**Total**", totals_from_row(rr["fleet"]["Fuel"])))
    return md_table(GROUP_HEADERS, rows)


def region_recs_from_region(rr, codes=None):
    out = []
    for code, r in rr["regions"].items():
        if codes is not None and code not in codes:
            continue
        out.append({"code": code, "rep": r["rep"] or "N/A", "t": totals_from_row(r)})

    def key(x):
        try:
            return (0, int(x["code"]))
        except ValueError:
            return (1, x["code"])
    return sorted(out, key=key)


def ttc_fleet_table(rr):
    """Fleet-wide Truck Care totals: the Tires / PM / TCE / Labor charts from the weekly sales call."""
    rows = []
    for sheet in TTC_METRIC_SHEETS:
        r = rr["fleet"].get(sheet)
        if not r:
            continue
        unit = TTC_METRIC_UNITS.get(sheet, "")
        nd = 2 if unit == "$" else 0
        cur = round(r["current"], nd) if r["current"] is not None else None
        ly = round(r["current"] - r["yoy"], nd) if (r["current"] is not None and r["yoy"] is not None) else None
        yoy = round(cur - ly, nd) if (cur is not None and ly is not None) else None
        v = r["vs_avg_pct"]
        rows.append([sheet, fmt_plain(cur, unit), fmt_plain(ly, unit), fmt_signed(yoy, unit),
                     pct(r["yoy"], (r["current"] - r["yoy"]) if (r["current"] is not None and r["yoy"] is not None) else None),
                     fmt_plain(r["avg"], unit), "N/A" if v is None else f"{'+' if v > 0 else ''}{v:.1f}%"])
    return md_table(["Metric", "This Week", "Same Week Last Year", "YoY vs Same Wk LY", "YoY vs Same Wk LY %", "13Wk Avg", "vs. 13Wk Avg"], rows), len(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# Fuel tables
# ═══════════════════════════════════════════════════════════════════════════════
def headline_table(t, scope=None):
    rows = [
        ["This week vs. prior week", fmt_plain(t["current"], "GAL"), fmt_plain(t["prior"], "GAL"),
         fmt_signed(t["wow"], "GAL"), pct(t["wow"], t["prior"])],
        ["This week vs. 13-week average", fmt_plain(t["current"], "GAL"), fmt_plain(t["avg"], "GAL"),
         fmt_signed(t["vs_avg"], "GAL"), pct(t["vs_avg"], t["avg"])],
        ["This week vs. same week last year", fmt_plain(t["current"], "GAL"), fmt_plain(t["ly"], "GAL"),
         fmt_signed(t["yoy"], "GAL"), pct(t["yoy"], t["ly"])],
        ["13-week average vs. last year's 13-week average", fmt_plain(t["avg"], "GAL"), fmt_plain(t["ly_avg"], "GAL"),
         fmt_signed(t["avg_yoy"], "GAL"), pct(t["avg_yoy"], t["ly_avg"])],
    ]
    return md_table([f"Measure ({scope})" if scope else "Measure", "Current", "Comparison", "Change (GAL)", "Change (%)"], rows)


def group_map(alignment):
    """region code -> group name (National / East / West / Inside East / ...)."""
    m = {}
    for name, codes in alignment["groups"].items():
        for c in codes:
            m[c] = name
    return m


def group_table(accts, alignment):
    gmap = group_map(alignment)
    buckets = {}
    for a in accts:
        buckets.setdefault(_merged_name(gmap.get(a["region"], NOT_ALIGNED)), []).append(a)
    order = []
    for g in alignment["groups"]:
        n = _merged_name(g)
        if n in buckets and n not in order:
            order.append(n)
    if NOT_ALIGNED in buckets:
        order.append(NOT_ALIGNED)
    rows = [group_row(g, totals(buckets[g])) for g in order]
    rows.append(group_row("**Total**", totals(accts)))
    return md_table(GROUP_HEADERS, rows), buckets


def region_rollups(accts, alignment):
    """One record per region number, sorted by region."""
    by = {}
    for a in accts:
        by.setdefault(a["region"], []).append(a)
    out = []
    for code, lst in by.items():
        t = totals(lst)
        entry = alignment["regions"].get(code)
        rep = entry["rep"] if entry and entry["rep"] else "N/A"
        out.append({"code": code, "rep": rep, "t": t, "accounts": lst})

    def key(r):
        try:
            return (0, int(r["code"]))
        except ValueError:
            return (1, r["code"])
    return sorted(out, key=key)


def region_rows(recs):
    return [[f"Region {r['code']}", r["rep"], fmt_plain(r["t"]["current"], "GAL"), fmt_signed(r["t"]["wow"], "GAL"),
             pct(r["t"]["vs_avg"], r["t"]["avg"]), fmt_signed(r["t"]["yoy"], "GAL"), pct(r["t"]["yoy"], r["t"]["ly"]),
             fmt_signed(r["t"]["avg_yoy"], "GAL"), pct(r["t"]["avg_yoy"], r["t"]["ly_avg"])]
            for r in recs]


REGION_HEADERS = ["Region", "Rep", "This Week", "WoW Change (GAL)", "vs 13Wk Avg %",
                  "YoY vs Same Wk LY (GAL)", "YoY vs Same Wk LY %", "13Wk Avg YoY (GAL)", "13Wk Avg YoY %"]


MOVE_CAP_PCT = 30.0


def _moved_30_or_more(a):
    """True when the week-over-week move is 30% or more (a jump from zero counts as 30% or more)."""
    if a["prior"] is None or a["current"] is None:
        return False
    chg = a["current"] - a["prior"]
    if a["prior"] <= 0:
        return chg != 0
    return abs(chg) / a["prior"] * 100 >= MOVE_CAP_PCT


def pick_decreases(accts, n, exclude_30=False):
    out = []
    for a in accts:
        if a["current"] is None or a["prior"] is None:
            continue
        chg = a["current"] - a["prior"]
        if chg >= 0:
            continue
        if exclude_30 and _moved_30_or_more(a):
            continue
        out.append(dict(a, chg=chg))
    out.sort(key=lambda x: x["chg"])
    return out[:n]


def pick_increases(accts, n, exclude_30=False):
    out = []
    for a in accts:
        if a["current"] is None or a["prior"] is None:
            continue
        chg = a["current"] - a["prior"]
        if chg <= 0:
            continue
        if exclude_30 and _moved_30_or_more(a):
            continue
        out.append(dict(a, chg=chg))
    out.sort(key=lambda x: x["chg"], reverse=True)
    return out[:n]


def pick_dark(accts, n):
    """Same definition as the rep briefs: nothing reported this week, 13-week average >= 1,000 GAL,
    and the customer isn't one that also shows a real increase in another line."""
    increase_names = set()
    for a in accts:
        if a["current"] is not None and a["prior"] is not None and a["current"] - a["prior"] >= INCREASE_MIN_GAL:
            increase_names.add(a["customer"])
    out = [a for a in accts
           if a["current"] is None and (a["avg_13wk"] or 0) >= NEWLY_DARK_MIN_GAL and a["customer"] not in increase_names]
    out.sort(key=lambda x: x["avg_13wk"] or 0, reverse=True)
    return out[:n]


CHANGE_HEADERS = ["Account", "Region", "Rep", "This Week", "Prior Week", "WoW Change", "YoY vs Same Wk LY"]


def change_rows(lst):
    return [[a["customer"], a["region"], a["rep"] or "N/A", fmt_plain(a["current"], "GAL"), fmt_plain(a["prior"], "GAL"),
             fmt_signed(a["chg"], "GAL"), fmt_signed(a["yoy_week"], "GAL")] for a in lst]


DARK_HEADERS = ["Account", "Region", "Rep", "13Wk Avg", "This Week", "Last Known Volume", "YoY vs Same Wk LY"]


def dark_rows(lst):
    return [[a["customer"], a["region"], a["rep"] or "N/A", fmt_plain(a["avg_13wk"], "GAL"), "0 GAL",
             fmt_plain(a["last_known"], "GAL"), fmt_signed(a["yoy_week"], "GAL")] for a in lst]


# ═══════════════════════════════════════════════════════════════════════════════
# Truck Care tables (executive only)
# ═══════════════════════════════════════════════════════════════════════════════
TTC_TEAM = lambda m: TTC_INSIDE_LABEL if m == "Inside" else TTC_EMAIL_LABELS.get(m, m)  # noqa: E731


def ttc_inside_view(ttc_results):
    """The Inside Sales Truck Care team, shaped like one more 'manager' so the same table builders can be reused."""
    if not ttc_results or not ttc_results.get("inside_rollups"):
        return None
    return {"manager_rollups": {"Inside": ttc_results["inside_rollups"]},
            "customer_records": {"Inside": ttc_results.get("inside_customer_records", {})}}


def ttc_summary_table(ttc_results, managers=None):
    rows = []
    for m in (managers or TTC_KNOWN_MANAGERS):
        for sheet in TTC_METRIC_SHEETS:
            r = ttc_results.get("manager_rollups", {}).get(m, {}).get(sheet)
            if not r:
                continue
            unit = TTC_METRIC_UNITS.get(sheet, "")
            vs_avg = r.get("curr_ov_avg")
            vs_avg_txt = "N/A" if vs_avg is None else f"{'+' if vs_avg > 0 else ''}{vs_avg:.1f}%"
            rows.append([TTC_TEAM(m), sheet, fmt_plain(r["this_week"], unit), fmt_plain(r["avg_13wk"], unit),
                         vs_avg_txt, fmt_signed(r["yoy"], unit)])
    return md_table(["Team", "Metric", "This Week", "13Wk Avg", "vs. 13Wk Avg", "YoY vs Same Wk LY"], rows), len(rows)


def ttc_decline_lists(ttc_results, n, exclude_30=False, managers=None):
    """Top-n biggest week-over-week declines per Truck Care metric, across all three teams.
    Tires / PM / Labor Hrs are counts, so a blank this week means zero. $ per truck is a ratio, so it needs both weeks.
    Customers with no activity at all in that metric (nothing this week, last week or on the 13-week average)
    are never listed."""
    out = {}
    for sheet in TTC_METRIC_SHEETS:
        unit = TTC_METRIC_UNITS.get(sheet, "")
        additive = sheet != "TCE Spend per Truck"
        merged = {}
        for m in (managers or TTC_KNOWN_MANAGERS):
            for rec in ttc_results.get("customer_records", {}).get(m, {}).get(sheet, []):
                tw, pw = rec.get("this_week"), rec.get("prior_week")
                if not ((rec.get("avg_13wk") or 0) > 0 or (tw or 0) > 0 or (pw or 0) > 0):
                    continue  # this customer doesn't buy this Truck Care service
                if additive:
                    if tw is None and pw is None:
                        continue
                    tw, pw = tw or 0, pw or 0
                elif tw is None or pw is None:
                    continue
                key = (m, rec["customer"], rec["rep"]) if additive else (m, rec["customer"], rec["rep"], id(rec))
                cur = merged.get(key)
                if cur is None:
                    merged[key] = {"customer": rec["customer"], "team": TTC_TEAM(m), "rep": rec["rep"] or "N/A",
                                   "this_week": tw, "prior_week": pw, "yoy": rec.get("yoy")}
                else:
                    cur["this_week"] += tw
                    cur["prior_week"] += pw
                    cur["yoy"] = _add(cur["yoy"], rec.get("yoy"))
        lst = []
        for v in merged.values():
            v["delta"] = v["this_week"] - v["prior_week"]
            if v["delta"] < 0:
                if exclude_30 and v["prior_week"] > 0 and abs(v["delta"]) / v["prior_week"] * 100 >= MOVE_CAP_PCT:
                    continue
                lst.append(v)
        lst.sort(key=lambda x: x["delta"])
        lst = lst[:n]
        rows = [[v["customer"], v["team"], v["rep"], fmt_plain(v["this_week"], unit), fmt_plain(v["prior_week"], unit),
                 fmt_signed(v["delta"], unit), fmt_signed(v["yoy"], unit)] for v in lst]
        out[sheet] = {
            "unit": unit, "items": lst,
            "table": md_table(["Account", "Team", "TTC Rep", "This Week", "Prior Week", "WoW Change", "YoY vs Same Wk LY"], rows),
        }
    return out


TTC_TOKEN = {"Tires": "%%EXEC_TTC_TIRES%%", "PM": "%%EXEC_TTC_PM%%",
             "TCE Spend per Truck": "%%EXEC_TTC_TCE%%", "Labor Hrs": "%%EXEC_TTC_LABOR%%"}
TTC_HEADING = {"Tires": "Tires (EA)", "PM": "PM Packages (EA)",
               "TCE Spend per Truck": "TCE Spend per Truck ($)", "Labor Hrs": "Labor Hours (Hrs)"}


# ═══════════════════════════════════════════════════════════════════════════════
# Prompt pieces
# ═══════════════════════════════════════════════════════════════════════════════
RULES = """ABSOLUTE RULE ON TABLES -- READ CAREFULLY: You do not build tables in this report. Every place a table belongs, this document tells you to output one exact placeholder token (formatted like %%SOMETHING%%) on its own line, by itself, with nothing else on that line. That token is swapped for the real table automatically after you respond. If you write anything other than the bare token on that line, it will be visibly wrong in the final report and it will be your error. The "for context only" data below is for writing bullet commentary ONLY.

ABSOLUTE RULE ON NUMBERS: every figure is already calculated. Quote figures exactly as they appear in this document. Never add, subtract, average, round differently, or convert anything into a new percentage. Never compute a percentage for an individual account -- gallons only.

TONE AND STYLE:
- Write as a senior analyst. Direct, confident, factual.
- Present information as observations and insights -- not directives or prescriptions.
- Never tell leadership what to do or how to respond. Surface the data and let them draw conclusions.
- Never call out gaps, failures, or accountability issues. State facts neutrally.
- Never write: "it is worth noting", "as we can see", "it appears that", "please note", "requires immediate action", "should follow up", "accountability gap"
- Numbers must always include units (GAL, EA, $, Hrs)
- Keep sections tight -- no extra blank lines between sections, no padding
- Minimize bold formatting. Use bold only for section headers, never for account names, rep names, metrics, or numbers in the text.
- Never use backticks or code formatting anywhere in your response, for any reason, under any circumstances.
- Never fabricate data."""


def _ctx_list(title, lines):
    out = [f"\n{title}:"]
    out += [f"  {l}" for l in lines] if lines else ["  (none)"]
    return out


def _change_ctx(lst):
    return [f"{a['customer']} | Region {a['region']} | Rep: {a['rep'] or 'N/A'} | This week {fmt_plain(a['current'], 'GAL')} | "
            f"Prior week {fmt_plain(a['prior'], 'GAL')} | WoW {fmt_signed(a['chg'], 'GAL')} | YoY {fmt_signed(a['yoy_week'], 'GAL')}"
            for a in lst]


def _dark_ctx(lst):
    return [f"{a['customer']} | Region {a['region']} | Rep: {a['rep'] or 'N/A'} | 13Wk Avg {fmt_plain(a['avg_13wk'], 'GAL')} | "
            f"Last known {fmt_plain(a['last_known'], 'GAL')} | YoY {fmt_signed(a['yoy_week'], 'GAL')}" for a in lst]


def _headline_ctx(t):
    return [
        f"This week: {fmt_plain(t['current'], 'GAL')} | Prior week: {fmt_plain(t['prior'], 'GAL')} | WoW: {fmt_signed(t['wow'], 'GAL')} ({pct(t['wow'], t['prior'])})",
        f"13-week average: {fmt_plain(t['avg'], 'GAL')} | This week vs. average: {fmt_signed(t['vs_avg'], 'GAL')} ({pct(t['vs_avg'], t['avg'])})",
        f"Same week last year: {fmt_plain(t['ly'], 'GAL')} | YoY: {fmt_signed(t['yoy'], 'GAL')} ({pct(t['yoy'], t['ly'])})",
        f"13-week average vs. last year's 13-week average: {fmt_signed(t['avg_yoy'], 'GAL')} ({pct(t['avg_yoy'], t['ly_avg'])})",
    ]


def _number_sections(sections):
    return "\n\n".join(f"## {i}. {title}\n{body}" for i, (title, body) in enumerate(sections, start=1))


# ═══════════════════════════════════════════════════════════════════════════════
# Executive summary
# ═══════════════════════════════════════════════════════════════════════════════
def build_exec_prompt(accts, alignment, report_date, ttc_results=None, region_report=None, n=LEADERSHIP_TOP_N):
    # Fleet / group / region totals: straight from the fleet Region report when it was uploaded (these are the
    # numbers on the executives' weekly graphs). Otherwise they are summed from the customer report.
    if region_report:
        t = totals_from_row(region_report["fleet"]["Fuel"])
        gtable = group_table_from_region(region_report)
        group_ctx_src = [(g, totals_from_row(r)) for g, r in merged_groups(region_report).items()]
        recs = [r for r in region_recs_from_region(region_report) if r["t"]["ly"] > 0]
    else:
        t = totals(accts)
        gtable, buckets = group_table(accts, alignment)
        group_ctx_src = [(g, totals(lst)) for g, lst in buckets.items()]
        recs = [r for r in region_rollups(accts, alignment) if r["t"]["ly"] > 0]
    ranked = sorted(recs, key=lambda r: r["t"]["yoy"], reverse=True)
    up = [r for r in ranked if r["t"]["yoy"] > 0][:5]
    down = [r for r in reversed(ranked) if r["t"]["yoy"] < 0][:5]

    list_accts = [a for a in accts if a["region"] not in EXEC_LIST_EXCLUDED_REGIONS]
    dec = pick_decreases(list_accts, n, exclude_30=EXEC_EXCLUDE_30PCT_MOVES)
    dark = pick_dark(list_accts, n)
    inc = pick_increases(list_accts, n, exclude_30=EXEC_EXCLUDE_30PCT_MOVES)

    table_map = {
        "%%EXEC_HEADLINE%%": headline_table(t),
        "%%EXEC_GROUP_TABLE%%": gtable,
        "%%EXEC_REGION_UP%%": md_table(REGION_HEADERS, region_rows(up)),
        "%%EXEC_REGION_DOWN%%": md_table(REGION_HEADERS, region_rows(down)),
        "%%EXEC_DEC%%": md_table(CHANGE_HEADERS, change_rows(dec)),
        "%%EXEC_DARK%%": md_table(DARK_HEADERS, dark_rows(dark)),
        "%%EXEC_INC%%": md_table(CHANGE_HEADERS, change_rows(inc)),
    }

    lines = [f"FLEET SALES EXECUTIVE SUMMARY — Period Ending {report_date}", "=" * 60,
             "\nSCOPE: fleet, group and region totals cover the whole fleet (all regions); the top-10 account lists come from the "
             "13-week customer report. YoY compares this week to the same week last year."]
    lines += _ctx_list("FLEET FUEL HEADLINE (for context only)", _headline_ctx(t))
    group_ctx = []
    for g, gt in group_ctx_src:
        group_ctx.append(f"{g}: this week {fmt_plain(gt['current'], 'GAL')} | YoY vs same week last year {fmt_signed(gt['yoy'], 'GAL')} ({pct(gt['yoy'], gt['ly'])}) | "
                         f"vs 13-week average {pct(gt['vs_avg'], gt['avg'])} | 13-week average YoY {fmt_signed(gt['avg_yoy'], 'GAL')} ({pct(gt['avg_yoy'], gt['ly_avg'])}) | WoW {fmt_signed(gt['wow'], 'GAL')}")
    lines += _ctx_list("REGION GROUPS (for context only)", group_ctx)
    lines += _ctx_list("STRONGEST REGIONS VS. LAST YEAR (for context only)",
                       [f"Region {r['code']} ({r['rep']}): YoY vs same week last year {fmt_signed(r['t']['yoy'], 'GAL')} ({pct(r['t']['yoy'], r['t']['ly'])}) | vs 13-week average {pct(r['t']['vs_avg'], r['t']['avg'])} | 13-week average YoY {pct(r['t']['avg_yoy'], r['t']['ly_avg'])}" for r in up])
    lines += _ctx_list("WEAKEST REGIONS VS. LAST YEAR (for context only)",
                       [f"Region {r['code']} ({r['rep']}): YoY vs same week last year {fmt_signed(r['t']['yoy'], 'GAL')} ({pct(r['t']['yoy'], r['t']['ly'])}) | vs 13-week average {pct(r['t']['vs_avg'], r['t']['avg'])} | 13-week average YoY {pct(r['t']['avg_yoy'], r['t']['ly_avg'])}" for r in down])
    lines += _ctx_list(f"TOP {n} BIGGEST WEEK-OVER-WEEK DECREASES (for context only)", _change_ctx(dec))
    lines += _ctx_list(f"TOP {n} NEWLY DARK ACCOUNTS (for context only)", _dark_ctx(dark))
    lines += _ctx_list(f"TOP {n} BIGGEST WEEK-OVER-WEEK INCREASES (for context only)", _change_ctx(inc))

    has_ttc = bool(ttc_results)
    flagged = len(dec) + len(dark) + len(inc)
    has_ttc_fleet = bool(region_report) and any(m in region_report["fleet"] for m in TTC_METRIC_SHEETS)
    if has_ttc_fleet:
        fleet_table, _ = ttc_fleet_table(region_report)
        table_map["%%EXEC_TTC_FLEET%%"] = fleet_table
        fleet_ctx = []
        for sheet in TTC_METRIC_SHEETS:
            r = region_report["fleet"].get(sheet)
            if r:
                u = TTC_METRIC_UNITS.get(sheet, "")
                nd = 2 if u == "$" else 0
                cur_r = round(r["current"], nd) if r["current"] is not None else None
                ly = round(r["current"] - r["yoy"], nd) if (r["current"] is not None and r["yoy"] is not None) else None
                yoy_r = round(cur_r - ly, nd) if (cur_r is not None and ly is not None) else None
                fleet_ctx.append(f"{sheet}: this week {fmt_plain(cur_r, u)} | same week last year {fmt_plain(ly, u)} | YoY {fmt_signed(yoy_r, u)} ({pct(r['yoy'], (r['current'] - r['yoy']) if (r['current'] is not None and r['yoy'] is not None) else None)})")
        lines += _ctx_list("TRUCK CARE FLEET-WIDE TOTALS (for context only)", fleet_ctx)
    if has_ttc:
        sum_table, sum_rows = ttc_summary_table(ttc_results)
        table_map["%%EXEC_TTC_SUMMARY%%"] = sum_table
        declines = ttc_decline_lists(ttc_results, n, exclude_30=EXEC_TTC_EXCLUDE_30PCT_MOVES)
        for sheet in TTC_METRIC_SHEETS:
            table_map[TTC_TOKEN[sheet]] = declines[sheet]["table"]
            flagged += len(declines[sheet]["items"])
        ttc_ctx = []
        for m in TTC_KNOWN_MANAGERS:
            for sheet in TTC_METRIC_SHEETS:
                r = ttc_results.get("manager_rollups", {}).get(m, {}).get(sheet)
                if r:
                    u = TTC_METRIC_UNITS.get(sheet, "")
                    ttc_ctx.append(f"{TTC_TEAM(m)} | {sheet}: this week {fmt_plain(r['this_week'], u)} | 13Wk avg {fmt_plain(r['avg_13wk'], u)} | YoY {fmt_signed(r['yoy'], u)}")
        lines += _ctx_list("TRUCK CARE TEAM SUMMARY (for context only)", ttc_ctx)
        for sheet in TTC_METRIC_SHEETS:
            u = declines[sheet]["unit"]
            lines += _ctx_list(f"TOP {n} TRUCK CARE DECLINES — {TTC_HEADING[sheet]} (for context only)",
                               [f"{v['customer']} | {v['team']} | This week {fmt_plain(v['this_week'], u)} | Prior {fmt_plain(v['prior_week'], u)} | WoW {fmt_signed(v['delta'], u)} | YoY {fmt_signed(v['yoy'], u)}"
                                for v in declines[sheet]["items"]])

    sections = [
        ("FUEL VOLUME — YEAR OVER YEAR",
         "On its own line, output exactly: %%EXEC_HEADLINE%%\nAfter the token: 2-3 bullets. Lead with the YoY result for the week and the 13-week average YoY result, then the week-over-week and vs.-average movement. Quote the figures from the headline above."),
        ("YEAR OVER YEAR BY REGION GROUP",
         "On its own line, output exactly: %%EXEC_GROUP_TABLE%%\n### Strongest Regions vs. Last Year\nOn its own line, output exactly: %%EXEC_REGION_UP%%\n### Weakest Regions vs. Last Year\nOn its own line, output exactly: %%EXEC_REGION_DOWN%%\nAfter the three tokens: 2-3 bullets on which groups and regions are driving the YoY result."),
        (f"TOP {n} BIGGEST DECREASES (WEEK OVER WEEK, GALLONS)",
         "On its own line, output exactly: %%EXEC_DEC%%\nAfter the token: 2 bullets on concentration by region or rep and the size of the largest losses."),
        (f"TOP {n} NEWLY DARK ACCOUNTS",
         "On its own line, output exactly: %%EXEC_DARK%%\nAfter the token: 2 bullets on the largest dark accounts and any region or rep concentration."),
        (f"TOP {n} BIGGEST INCREASES (WEEK OVER WEEK, GALLONS)",
         "On its own line, output exactly: %%EXEC_INC%%\nAfter the token: 2 bullets on the largest gainers."),
    ]
    if has_ttc or has_ttc_fleet:
        ttc_body = []
        if has_ttc_fleet:
            ttc_body.append("### Fleet-Wide Totals\nOn its own line, output exactly: %%EXEC_TTC_FLEET%%")
        if has_ttc:
            ttc_body.append("### By Team\nOn its own line, output exactly: %%EXEC_TTC_SUMMARY%%")
        ttc_body.append("After the table token(s) above: 2-3 bullets on the YoY direction for Tires, PM, TCE Spend per Truck and Labor Hours.")
    if has_ttc:
        ttc_body.append(f"### Top {n} Declines by Metric (week over week)")
        for sheet in TTC_METRIC_SHEETS:
            ttc_body.append(f"#### {TTC_HEADING[sheet]}\nOn its own line, output exactly: {TTC_TOKEN[sheet]}")
        ttc_body.append("After all four tokens: 2-3 bullets on the largest declines and any accounts that appear under more than one metric.")
    if has_ttc or has_ttc_fleet:
        sections.append(("TRUCK CARE", "\n".join(ttc_body)))
    sections.append(("KEY TAKEAWAYS", "3 bullets. Each names a specific account, region or team, states a specific number from this document, and surfaces an observation."))
    sections.append(("CLOSING", "One sentence. Factual only."))

    prompt = "\n".join(lines) + f"""

---
INSTRUCTIONS:
You are the Fleet Sales Intelligence Agent for Love's Travel Stops fleet sales team. Write the executive summary for senior leadership. They focus on year-over-year numbers, so lead with YoY.

{RULES}

OUTPUT FORMAT -- follow this exact order:

## FLEET SALES EXECUTIVE SUMMARY
**Period Ending: {report_date}**

{_number_sections(sections)}
"""
    return prompt, table_map, flagged


# ═══════════════════════════════════════════════════════════════════════════════
# Regional VP summary (East / West): the executive summary limited to one side of the business
# ═══════════════════════════════════════════════════════════════════════════════
def build_vp_prompt(label, groups, ttc_managers, recipients, accts, alignment, report_date,
                    ttc_results=None, region_report=None, n=LEADERSHIP_TOP_N):
    codes = set()
    for g in groups:
        codes |= set(alignment["groups"].get(g) or [])
    scope_accts = [a for a in accts if a["region"] in codes]
    member_rows = [region_report["groups"][g] for g in groups if region_report and g in region_report["groups"]]
    if region_report and len(member_rows) == len(groups):
        t = totals_from_row(merge_region_rows(member_rows, label))
        group_ctx_src = [(g, totals_from_row(region_report["groups"][g])) for g in groups]
        recs = [r for r in region_recs_from_region(region_report, codes=codes) if r["t"]["ly"] > 0]
    else:
        gmap = group_map(alignment)
        t = totals(scope_accts)
        group_ctx_src = [(g, totals([a for a in scope_accts if gmap.get(a["region"]) == g])) for g in groups]
        recs = [r for r in region_rollups(scope_accts, alignment) if r["t"]["ly"] > 0]
    gtable = md_table(GROUP_HEADERS, [group_row(g, gt) for g, gt in group_ctx_src] + [group_row(f"**Total ({' + '.join(groups)})**", t)])
    ranked = sorted(recs, key=lambda r: r["t"]["yoy"], reverse=True)
    up = [r for r in ranked if r["t"]["yoy"] > 0][:5]
    down = [r for r in reversed(ranked) if r["t"]["yoy"] < 0][:5]

    list_accts = [a for a in scope_accts if a["region"] not in EXEC_LIST_EXCLUDED_REGIONS]
    dec = pick_decreases(list_accts, n, exclude_30=EXEC_EXCLUDE_30PCT_MOVES)
    dark = pick_dark(list_accts, n)
    inc = pick_increases(list_accts, n, exclude_30=EXEC_EXCLUDE_30PCT_MOVES)

    table_map = {
        "%%VP_HEADLINE%%": headline_table(t, " + ".join(groups)),
        "%%VP_GROUP_TABLE%%": gtable,
        "%%VP_REGION_UP%%": md_table(REGION_HEADERS, region_rows(up)),
        "%%VP_REGION_DOWN%%": md_table(REGION_HEADERS, region_rows(down)),
        "%%VP_DEC%%": md_table(CHANGE_HEADERS, change_rows(dec)),
        "%%VP_DARK%%": md_table(DARK_HEADERS, dark_rows(dark)),
        "%%VP_INC%%": md_table(CHANGE_HEADERS, change_rows(inc)),
    }
    team_names = " and ".join(TTC_TEAM(m) for m in ttc_managers)
    lines = [f"{label.upper()} FLEET SALES EXECUTIVE SUMMARY — Period Ending {report_date}", "=" * 60,
             f"\nSCOPE: {label} only -- the {' and '.join(groups)} fuel accounts" + (f" and the {team_names} Truck Care team" if ttc_results else "") +
             ". Nothing outside this scope is included. YoY compares this week to the same week last year."]
    lines += _ctx_list("FUEL HEADLINE (for context only)", _headline_ctx(t))
    group_ctx = []
    for g, gt in group_ctx_src:
        group_ctx.append(f"{g}: this week {fmt_plain(gt['current'], 'GAL')} | YoY vs same week last year {fmt_signed(gt['yoy'], 'GAL')} ({pct(gt['yoy'], gt['ly'])}) | "
                         f"vs 13-week average {pct(gt['vs_avg'], gt['avg'])} | 13-week average YoY {fmt_signed(gt['avg_yoy'], 'GAL')} ({pct(gt['avg_yoy'], gt['ly_avg'])}) | WoW {fmt_signed(gt['wow'], 'GAL')}")
    lines += _ctx_list("GROUPS (for context only)", group_ctx)
    reg_line = lambda r: (f"Region {r['code']} ({r['rep']}): YoY vs same week last year {fmt_signed(r['t']['yoy'], 'GAL')} ({pct(r['t']['yoy'], r['t']['ly'])}) | "  # noqa: E731
                          f"vs 13-week average {pct(r['t']['vs_avg'], r['t']['avg'])} | 13-week average YoY {pct(r['t']['avg_yoy'], r['t']['ly_avg'])}")
    lines += _ctx_list("STRONGEST REGIONS VS. LAST YEAR (for context only)", [reg_line(r) for r in up])
    lines += _ctx_list("WEAKEST REGIONS VS. LAST YEAR (for context only)", [reg_line(r) for r in down])
    lines += _ctx_list(f"TOP {n} BIGGEST WEEK-OVER-WEEK DECREASES (for context only)", _change_ctx(dec))
    lines += _ctx_list(f"TOP {n} NEWLY DARK ACCOUNTS (for context only)", _dark_ctx(dark))
    lines += _ctx_list(f"TOP {n} BIGGEST WEEK-OVER-WEEK INCREASES (for context only)", _change_ctx(inc))

    flagged = len(dec) + len(dark) + len(inc)
    has_ttc = bool(ttc_results) and any(ttc_results.get("manager_rollups", {}).get(m) for m in ttc_managers)
    if has_ttc:
        sum_table, _ = ttc_summary_table(ttc_results, ttc_managers)
        table_map["%%VP_TTC_SUMMARY%%"] = sum_table
        declines = ttc_decline_lists(ttc_results, n, exclude_30=EXEC_TTC_EXCLUDE_30PCT_MOVES, managers=ttc_managers)
        for sheet in TTC_METRIC_SHEETS:
            table_map[TTC_TOKEN[sheet].replace("EXEC_", "VP_")] = declines[sheet]["table"]
            flagged += len(declines[sheet]["items"])
        ttc_ctx = []
        for m in ttc_managers:
            for sheet in TTC_METRIC_SHEETS:
                r = ttc_results.get("manager_rollups", {}).get(m, {}).get(sheet)
                if r:
                    u = TTC_METRIC_UNITS.get(sheet, "")
                    ttc_ctx.append(f"{TTC_TEAM(m)} | {sheet}: this week {fmt_plain(r['this_week'], u)} | 13Wk avg {fmt_plain(r['avg_13wk'], u)} | YoY vs same week last year {fmt_signed(r['yoy'], u)}")
        lines += _ctx_list("TRUCK CARE TEAM SUMMARY (for context only)", ttc_ctx)
        for sheet in TTC_METRIC_SHEETS:
            u = declines[sheet]["unit"]
            lines += _ctx_list(f"TOP {n} TRUCK CARE DECLINES — {TTC_HEADING[sheet]} (for context only)",
                               [f"{v['customer']} | {v['team']} | This week {fmt_plain(v['this_week'], u)} | Prior {fmt_plain(v['prior_week'], u)} | WoW {fmt_signed(v['delta'], u)} | YoY {fmt_signed(v['yoy'], u)}"
                                for v in declines[sheet]["items"]])

    sections = [
        ("FUEL VOLUME — YEAR OVER YEAR",
         "On its own line, output exactly: %%VP_HEADLINE%%\nAfter the token: 2-3 bullets. Lead with the YoY result for the week and the 13-week average YoY result, then the week-over-week and vs.-average movement. Quote the figures from the headline above."),
        ("YEAR OVER YEAR BY GROUP",
         "On its own line, output exactly: %%VP_GROUP_TABLE%%\n### Strongest Regions vs. Last Year\nOn its own line, output exactly: %%VP_REGION_UP%%\n### Weakest Regions vs. Last Year\nOn its own line, output exactly: %%VP_REGION_DOWN%%\nAfter the three tokens: 2-3 bullets on which groups and regions are driving the YoY result."),
        (f"TOP {n} BIGGEST DECREASES (WEEK OVER WEEK, GALLONS)",
         "On its own line, output exactly: %%VP_DEC%%\nAfter the token: 2 bullets on concentration by region or rep and the size of the largest losses."),
        (f"TOP {n} NEWLY DARK ACCOUNTS",
         "On its own line, output exactly: %%VP_DARK%%\nAfter the token: 2 bullets on the largest dark accounts and any region or rep concentration."),
        (f"TOP {n} BIGGEST INCREASES (WEEK OVER WEEK, GALLONS)",
         "On its own line, output exactly: %%VP_INC%%\nAfter the token: 2 bullets on the largest gainers."),
    ]
    if has_ttc:
        ttc_body = ["### By Team\nOn its own line, output exactly: %%VP_TTC_SUMMARY%%",
                    "After the table token above: 2-3 bullets on the YoY direction for Tires, PM, TCE Spend per Truck and Labor Hours.",
                    f"### Top {n} Declines by Metric (week over week)"]
        for sheet in TTC_METRIC_SHEETS:
            ttc_body.append(f"#### {TTC_HEADING[sheet]}\nOn its own line, output exactly: {TTC_TOKEN[sheet].replace('EXEC_', 'VP_')}")
        ttc_body.append("After all four tokens: 2-3 bullets on the largest declines and any accounts that appear under more than one metric.")
        sections.append(("TRUCK CARE", "\n".join(ttc_body)))
    sections.append(("KEY TAKEAWAYS", "3 bullets. Each names a specific account (with its region), region or team, states a specific number from this document, and surfaces an observation."))
    sections.append(("CLOSING", "One sentence. Factual only."))

    prompt = "\n".join(lines) + f"""

---
INSTRUCTIONS:
You are the Fleet Sales Intelligence Agent for Love's Travel Stops fleet sales team. Write the executive summary for the {label} vice president ({' and '.join(recipients)}). They focus on year-over-year numbers, so lead with YoY. Cover {label} only: do not mention other regions, other groups, national accounts, or any fleet-wide total.

{RULES}

OUTPUT FORMAT -- follow this exact order:

## {label.upper()} FLEET SALES EXECUTIVE SUMMARY
**Period Ending: {report_date}**

{_number_sections(sections)}
"""
    return prompt, table_map, flagged


# ═══════════════════════════════════════════════════════════════════════════════
# Manager brief (Inside Sales = Inside East + Inside West, one email to both managers)
# ═══════════════════════════════════════════════════════════════════════════════
def build_manager_prompt(label, groups, managers, accts, alignment, report_date, region_report=None, n=MANAGER_TOP_N, ttc_results=None):
    codes = set()
    for g in groups:
        codes |= set(alignment["groups"].get(g) or [])
    # Group and region totals come from the fleet Region report when it was uploaded (matches the executives' graphs).
    member_rows = [region_report["groups"][g] for g in groups if region_report and g in region_report["groups"]]
    if region_report and len(member_rows) == len(groups):
        t = totals_from_row(merge_region_rows(member_rows, label))
        recs = region_recs_from_region(region_report, codes=codes)
    else:
        t = totals(accts)
        recs = region_rollups(accts, alignment)
    dec = pick_decreases(accts, n)
    dark = pick_dark(accts, n)
    inc = pick_increases(accts, n)

    table_map = {
        "%%MGR_HEADLINE%%": headline_table(t, " + ".join(groups)),
        "%%MGR_REGIONS%%": md_table(REGION_HEADERS, region_rows(recs)),
        "%%MGR_DEC%%": md_table(CHANGE_HEADERS, change_rows(dec)),
        "%%MGR_DARK%%": md_table(DARK_HEADERS, dark_rows(dark)),
        "%%MGR_INC%%": md_table(CHANGE_HEADERS, change_rows(inc)),
    }
    lines = [f"{label.upper()} WEEKLY BRIEF — Period Ending {report_date}", "=" * 60,
             f"\nSCOPE: every fuel customer in the regions that report into {label} (Inside East and Inside West together, treated as one group). "
             "Nothing outside this group is included. YoY compares this week to the same week last year."]
    lines += _ctx_list("GROUP FUEL HEADLINE (for context only)", _headline_ctx(t))
    lines += _ctx_list("REGIONS (for context only)",
                       [f"Region {r['code']} ({r['rep']}): this week {fmt_plain(r['t']['current'], 'GAL')} | WoW {fmt_signed(r['t']['wow'], 'GAL')} | "
                        f"vs 13-week average {pct(r['t']['vs_avg'], r['t']['avg'])} | YoY vs same week last year {fmt_signed(r['t']['yoy'], 'GAL')} ({pct(r['t']['yoy'], r['t']['ly'])}) | "
                        f"13-week average YoY {fmt_signed(r['t']['avg_yoy'], 'GAL')} ({pct(r['t']['avg_yoy'], r['t']['ly_avg'])})" for r in recs])
    lines += _ctx_list(f"TOP {n} BIGGEST WEEK-OVER-WEEK DECREASES (for context only)", _change_ctx(dec))
    lines += _ctx_list(f"TOP {n} NEWLY DARK ACCOUNTS (for context only)", _dark_ctx(dark))
    lines += _ctx_list(f"TOP {n} BIGGEST WEEK-OVER-WEEK INCREASES (for context only)", _change_ctx(inc))

    flagged = len(dec) + len(dark) + len(inc)
    inside_ttc = ttc_inside_view(ttc_results)
    if inside_ttc:
        sum_table, _ = ttc_summary_table(inside_ttc, ["Inside"])
        table_map["%%MGR_TTC_SUMMARY%%"] = sum_table
        declines = ttc_decline_lists(inside_ttc, n, exclude_30=EXEC_TTC_EXCLUDE_30PCT_MOVES, managers=["Inside"])
        for sheet in TTC_METRIC_SHEETS:
            table_map[TTC_TOKEN[sheet].replace("EXEC_", "MGR_")] = declines[sheet]["table"]
            flagged += len(declines[sheet]["items"])
        ttc_ctx = []
        for sheet in TTC_METRIC_SHEETS:
            r = inside_ttc["manager_rollups"]["Inside"].get(sheet)
            if r:
                u = TTC_METRIC_UNITS.get(sheet, "")
                ttc_ctx.append(f"{TTC_TEAM('Inside')} | {sheet}: this week {fmt_plain(r['this_week'], u)} | 13Wk avg {fmt_plain(r['avg_13wk'], u)} | YoY vs same week last year {fmt_signed(r['yoy'], u)}")
        lines += _ctx_list("TRUCK CARE TEAM SUMMARY (for context only)", ttc_ctx)
        for sheet in TTC_METRIC_SHEETS:
            u = declines[sheet]["unit"]
            lines += _ctx_list(f"TOP {n} TRUCK CARE DECLINES — {TTC_HEADING[sheet]} (for context only)",
                               [f"{v['customer']} | {v['team']} | TTC rep {v['rep']} | This week {fmt_plain(v['this_week'], u)} | Prior {fmt_plain(v['prior_week'], u)} | WoW {fmt_signed(v['delta'], u)} | YoY {fmt_signed(v['yoy'], u)}"
                                for v in declines[sheet]["items"]])

    sections = [
        ("GROUP HEADLINE", "On its own line, output exactly: %%MGR_HEADLINE%%\nAfter the token: 2-3 bullets on the group's year-over-year result (this week vs. the same week last year, and the 13-week average vs. last year's 13-week average), week-over-week movement and position vs. the 13-week average."),
        ("REGIONS", "On its own line, output exactly: %%MGR_REGIONS%%\nAfter the token: 2-3 bullets on which regions are driving the group's result, up or down."),
        (f"TOP {n} DECREASES (WEEK OVER WEEK, GALLONS)", "On its own line, output exactly: %%MGR_DEC%%\nAfter the token: 1-2 bullets on rep or region concentration. Always say which region an account is in."),
        (f"TOP {n} NEWLY DARK ACCOUNTS", "On its own line, output exactly: %%MGR_DARK%%\nAfter the token: 1-2 bullets on the largest dark accounts. Always say which region an account is in."),
        (f"TOP {n} INCREASES (WEEK OVER WEEK, GALLONS)", "On its own line, output exactly: %%MGR_INC%%\nAfter the token: 1-2 bullets on the largest gainers. Always say which region an account is in."),
        ("KEY TAKEAWAYS", "3 bullets. Each names a specific account (with its region, or its team for Truck Care), region or rep, states a specific number from this document, and surfaces an observation."),
        ("CLOSING", "One sentence. Factual only."),
    ]
    if inside_ttc:
        ttc_body = ["### By Team\nOn its own line, output exactly: %%MGR_TTC_SUMMARY%%",
                    "After the table token above: 2-3 bullets on the YoY direction for Tires, PM, TCE Spend per Truck and Labor Hours.",
                    f"### Top {n} Declines by Metric (week over week)"]
        for sheet in TTC_METRIC_SHEETS:
            ttc_body.append(f"#### {TTC_HEADING[sheet]}\nOn its own line, output exactly: {TTC_TOKEN[sheet].replace('EXEC_', 'MGR_')}")
        ttc_body.append("After all four tokens: 2-3 bullets on the largest declines and any accounts that appear under more than one metric.")
        sections.insert(5, ("TRUCK CARE", "\n".join(ttc_body)))
    prompt = "\n".join(lines) + f"""

---
INSTRUCTIONS:
You are the Fleet Sales Intelligence Agent for Love's Travel Stops fleet sales team. Write a high-level weekly brief on {label} for its managers ({' and '.join(managers)}). Treat {label} as ONE group: never split it into Inside East and Inside West. Do not mention other groups, other managers, or any fleet-wide total.

{RULES}

OUTPUT FORMAT -- follow this exact order:

## {label.upper()} WEEKLY BRIEF
**Period Ending: {report_date}**

{_number_sections(sections)}
"""
    return prompt, table_map, flagged


# ═══════════════════════════════════════════════════════════════════════════════
# Plan items (same shape the rep emails use)
# ═══════════════════════════════════════════════════════════════════════════════
def _joined_first_names(names):
    firsts = [first_name(n) for n in names]
    if len(firsts) <= 1:
        return "".join(firsts)
    return ", ".join(firsts[:-1]) + " and " + firsts[-1]


def _same_date(a, b):
    def norm(x):
        m = re.match(r"\s*0?(\d{1,2})/0?(\d{1,2})/(\d{4})", str(x or ""))
        return m.groups() if m else str(x or "").strip()
    return norm(a) == norm(b)


def build_leadership_items(fuel_path, alignment, report_date, ttc_results=None, region_report=None):
    """Returns (items, skipped): the executive summary plus one roll-up per configured manager group.
    region_report = read_region_report(...) of the fleet Region ('Graphs') report, or None."""
    items, skipped = [], []
    region_notes = []
    if region_report is None:
        region_notes.append("No fleet Region (Graphs) report uploaded -- fleet, group and region totals are summed from the "
                            "customer report and can differ from the weekly sales-call graphs by a few thousand gallons")
    elif region_report.get("date") and not _same_date(region_report["date"], report_date):
        region_notes.append(f"The fleet Region report is dated {region_report['date']} but the customer report is dated {report_date} -- check you uploaded the same week")
    accts = aggregate_accounts(read_fuel_rows(fuel_path))
    if not accts:
        return items, [{"email": "Executive Summary", "reason": "No customer rows found on the Fuel tab"}]

    # ── Executive summary ──
    warnings = []
    to_list = []
    for name in EXEC_RECIPIENTS:
        addr = make_email(name)
        if addr:
            to_list.append(addr)
        else:
            warnings.append(f"Can't build an address for '{name}'")
    if not ttc_results:
        warnings.append("No Truck Care reports uploaded -- the executive summary will be fuel only")
    warnings += region_notes
    prompt, table_map, flagged = build_exec_prompt(accts, alignment, report_date, ttc_results, region_report)
    items.append({
        "id": "exec-summary", "kind": "exec", "label": "Executive Summary",
        "to_name": " / ".join(EXEC_RECIPIENTS),
        "greeting_name": _joined_first_names(EXEC_RECIPIENTS),
        "to": "; ".join(to_list), "cc": [],
        "subject": f"{EXEC_SUBJECT_LABEL} Period Ending {report_date}",
        "prompt": prompt, "table_map": table_map, "flagged": flagged,
        "warnings": warnings, "file_stem": "Executive_Summary",
    })

    # ── Regional VP summaries (East / West) ──
    for vp in VP_BRIEFS:
        label, groups, ttc_mgrs, recips = vp["label"], vp["groups"], vp["ttc_managers"], vp["recipients"]
        shown = f"{label} VP ({', '.join(recips)})"
        codes = set()
        for g in groups:
            codes |= set(alignment["groups"].get(g) or [])
        missing = [g for g in groups if not alignment["groups"].get(g)]
        if missing or not codes:
            skipped.append({"email": shown, "reason": "No " + " / ".join(f"'{g}'" for g in (missing or groups)) + " group on the alignment file's FUEL tab"})
            continue
        addrs, bad = [], []
        for r_ in recips:
            a_ = make_email(r_)
            (addrs if a_ else bad).append(a_ or r_)
        if bad:
            skipped.append({"email": shown, "reason": "Can't build an address from " + ", ".join(f"'{b_}'" for b_ in bad)})
            continue
        scope_accts = [a for a in accts if a["region"] in codes]
        if not scope_accts:
            skipped.append({"email": shown, "reason": f"No customers found for the {label} regions in this report"})
            continue
        warnings = []
        present = {a["region"] for a in scope_accts}
        open_codes = sorted(c for c in codes if c in present and is_open_seat((alignment["regions"].get(c) or {}).get("rep")))
        if open_codes:
            warnings.append("Includes open-seat region(s): " + ", ".join(open_codes))
        if not ttc_results:
            warnings.append("No Truck Care reports uploaded -- this summary will be fuel only")
        elif not any(ttc_results.get("manager_rollups", {}).get(m) for m in ttc_mgrs):
            warnings.append("No Truck Care data found for " + ", ".join(ttc_mgrs) + " -- this summary will be fuel only")
        warnings += region_notes
        prompt, table_map, flagged = build_vp_prompt(label, groups, ttc_mgrs, recips, accts, alignment, report_date, ttc_results, region_report)
        items.append({
            "id": f"vp-{label.lower()}", "kind": "exec", "label": shown,
            "to_name": " / ".join(recips), "greeting_name": _joined_first_names(recips),
            "to": "; ".join(addrs), "cc": [],
            "subject": f"{vp['subject']} Period Ending {report_date}",
            "prompt": prompt, "table_map": table_map, "flagged": flagged,
            "warnings": warnings, "file_stem": vp["file_stem"],
        })

    # ── Manager brief(s): one email addressed to every manager of the combined group ──
    for brief in MANAGER_BRIEFS:
        label, groups, managers = brief["label"], brief["groups"], brief["managers"]
        shown = f"{label} ({', '.join(managers)})"
        codes = set()
        missing = [g for g in groups if not alignment["groups"].get(g)]
        for g in groups:
            codes |= set(alignment["groups"].get(g) or [])
        if missing or not codes:
            skipped.append({"email": shown, "reason": "No " + " / ".join(f"'{g}'" for g in (missing or groups)) + " group on the alignment file's FUEL tab"})
            continue
        addrs, bad = [], []
        for m in managers:
            a_ = make_email(m)
            (addrs if a_ else bad).append(a_ or m)
        if bad:
            skipped.append({"email": shown, "reason": "Can't build an address from " + ", ".join(f"'{b_}'" for b_ in bad)})
            continue
        group_accts = [a for a in accts if a["region"] in codes]
        if not group_accts:
            skipped.append({"email": shown, "reason": f"No customers found for the {label} regions in this report"})
            continue
        warnings = []
        present = {a["region"] for a in group_accts}
        open_codes = sorted(c for c in codes
                            if c in present and is_open_seat((alignment["regions"].get(c) or {}).get("rep")))
        if open_codes:
            warnings.append("Includes open-seat region(s): " + ", ".join(open_codes))
        if not ttc_results:
            warnings.append("No Truck Care reports uploaded -- this brief will be fuel only")
        elif not ttc_inside_view(ttc_results):
            warnings.append("No Inside Sales Truck Care team found in the Truck Care reports -- this brief will be fuel only")
        warnings += region_notes
        prompt, table_map, flagged = build_manager_prompt(label, groups, managers, group_accts, alignment, report_date, region_report, ttc_results=ttc_results)
        items.append({
            "id": f"mgr-{label.lower().replace(' ', '-')}", "kind": "manager", "label": shown,
            "to_name": " / ".join(managers), "greeting_name": _joined_first_names(managers),
            "to": "; ".join(addrs), "cc": [],
            "subject": f"{brief['subject']} Period Ending {report_date}",
            "prompt": prompt, "table_map": table_map, "flagged": flagged,
            "warnings": warnings, "file_stem": brief["file_stem"],
        })
    return items, skipped
