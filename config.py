ANTHROPIC_API_KEY = ""

FUEL_DECREASE_BUCKETS = [
    (0,  10,  "0-10% Decrease"),
    (10, 20,  "10-20% Decrease"),
    (20, 30,  "20-30% Decrease"),
]

FUEL_MAIN_THRESHOLD_GAL = 10000
FUEL_MIN_DECREASE_GAL = 500      # a week-over-week fuel decrease smaller than this is never listed (rep briefs)
NON_FUEL_ALERT_PCT = 20
CUSTOMER_DATA_START_ROW = 7
REGION_DATA_START_ROW = 6

INSIDE_SALES_REGIONS = {"30", "31", "32", "33", "34", "35", "36", "37", "39", "40", "41", "43", "44"}
INSIDE_EAST_REGIONS = {"32", "33", "35", "37", "40", "43", "44"}
INSIDE_WEST_REGIONS = {"30", "31", "34", "36", "39", "41"}

CUSTOMER_COLS = {
    "region":       0,
    "customer":     1,
    "salesperson":  2,
    "area_manager": 3,
    "run_rate":     4,
    "avg_13wk":     5,
    "curr_ov_avg":  6,
    "yoy_cur_week": 7,
    "current_week": 8,
    "prior_week":   9,
    "yoy_avg":      21,
    "yoy_dsl_avg":  22,
}

REGION_COLS = {
    "customer":     0,
    "salesperson":  1,
    "run_rate":     2,
    "avg_13wk":     3,
    "curr_ov_avg":  4,
    "yoy_cur_week": 5,
    "current_week": 6,
    "prior_week":   7,
    "yoy_avg":      19,
    "yoy_dsl_avg":  20,
}

METRIC_SHEETS = ["Fuel", "Tires", "PM", "TCE Spend per Truck", "Labor Hrs"]
FUEL_SHEET = "Fuel"

METRIC_UNITS = {
    "Fuel":                "GAL",
    "Tires":               "EA",
    "PM":                  "EA",
    "TCE Spend per Truck": "$",
    "Labor Hrs":           "Hrs",
}

DEBUG = True
PORT = 5000
MAX_TOKENS = 8192

# ── Truck Care config additions ─────────────────────────────────────────────────

TTC_METRIC_SHEETS = ["Tires", "PM", "TCE Spend per Truck", "Labor Hrs"]
TTC_METRIC_UNITS = {"Tires": "EA", "PM": "EA", "TCE Spend per Truck": "$", "Labor Hrs": "Hrs"}

TTC_KNOWN_MANAGERS = ["Brett Moody", "Keith Taggart", "TJ Atwood"]
TTC_MANAGER_DISPLAY = {
    "Brett Moody": "Brett Moody (East)",
    "Keith Taggart": "Keith Taggart (TTC National Accounts)",
    "TJ Atwood": "TJ Atwood (West)",
}
TTC_INSIDE_MANAGER = "Brett Moody"  # no longer used for attribution (Inside is excluded entirely) -- kept for reference

# Customer file: uniform 21-column layout across all 4 metric sheets
TTC_CUSTOMER_COLS = {
    "rep": 0, "customer": 1, "salesperson": 2, "area_manager": 3,
    "run_rate": 4, "avg_13wk": 5, "curr_ov_avg": 6, "yoy": 7, "week_start": 8,
}
TTC_CUSTOMER_DATA_START_ROW = 6

# Region file: column layout differs for Labor Hrs (extra "Sales Person" dup column shifts everything +1)
TTC_REGION_COLS = {
    "Tires": {"name": 0, "run_rate": 1, "avg_13wk": 2, "curr_ov_avg": 3, "yoy": 4, "week_start": 5},
    "PM": {"name": 0, "run_rate": 1, "avg_13wk": 2, "curr_ov_avg": 3, "yoy": 4, "week_start": 5},
    "TCE Spend per Truck": {"name": 0, "run_rate": 1, "avg_13wk": 2, "curr_ov_avg": 3, "yoy": 4, "week_start": 5},
    "Labor Hrs": {"name": 0, "run_rate": 2, "avg_13wk": 3, "curr_ov_avg": 4, "yoy": 5, "week_start": 6},
}
TTC_WEEK_COUNT = 13

TTC_ALERT_THRESHOLDS = {"Tires": 15, "PM": 5, "TCE Spend per Truck": 500, "Labor Hrs": 10}

TTC_MONTHLY_TAB_BY_MANAGER = {"Keith Taggart": "National", "Brett Moody": "East", "TJ Atwood": "West"}

# ── Email automation (Phase 1: generate JSON files for Power Automate) ─────────
EMAIL_DOMAIN = "loves.com"                 # addresses are built as First.Last@loves.com
EMAIL_EXCLUDED_REGIONS = {"9"}             # Region 9 ("Other Programs") never gets an email
EMAIL_SIGNOFF = "Thank you,"
EMAIL_MODEL = "claude-opus-4-6"
EMAIL_MAX_WORKERS = 4                      # simultaneous Claude calls while generating briefs
EMAIL_MAX_TOKENS = MAX_TOKENS

# Used ONLY for the cost estimate shown before generating. Verify against your Anthropic Console.
PRICE_INPUT_PER_MTOK = 5.0                 # USD per million input tokens
PRICE_OUTPUT_PER_MTOK = 25.0               # USD per million output tokens

TTC_EMAIL_LABELS = {
    "Brett Moody": "TTC East",
    "Keith Taggart": "TTC National Accounts",
    "TJ Atwood": "TTC West",
}
TTC_INSIDE_LABEL = "TTC Inside Sales"      # the Inside Sales Truck Care team (shown in the Inside Sales brief only)

# Names whose email is NOT First.Last@loves.com. Key = full name exactly as it appears in the alignment file.
EMAIL_OVERRIDES = {
    "Peter Ungaro": "pete.ungaro@loves.com",
    "Stephen Kelly": "steve.kelly@loves.com",
    "Rigoberto Martinez": "rigo.martinez@loves.com",
    "Larry Masiulis": "Laurynas.Masiulis@loves.com",
    "Chris McGee": "Christopher.McGee@loves.com",
}

# ── Leadership emails (executive summary + the combined Inside Sales brief) ──────
EXEC_RECIPIENTS = ["Stephen Parker", "Jon Archard"]       # To: line of the executive summary (no CC)
EXEC_SUBJECT_LABEL = "Fleet Sales Executive Summary"
# One combined brief for the Inside Sales managers: every group in "groups" is merged into a single set of tables and sent
# as ONE email addressed To all "managers".
MANAGER_BRIEFS = [
    {"label": "Inside Sales",
     "groups": ["Inside East", "Inside West"],          # group names on the alignment file's FUEL tab
     "managers": ["Kelvin Ling", "Megan Dwarshuis", "Todd Wilson"],
     "subject": "Inside Sales Weekly Brief",
     "file_stem": "Inside_Sales_Weekly_Brief"},
]
# High-level summaries for the VP and the four quadrant leads. Each one is the executive layout limited to its own scope.
#   fuel: {"groups": [...]}   fuel groups from the alignment file's FUEL tab ("Inside Sales" = Inside East + Inside West, see GROUP_MERGES)
#         {"regions": [...]}  specific regions (a quadrant lead's regions; Region 29 is counted inside 26 -- see REGION_ROLLUPS)
#   ttc:  {"teams": [...]}    whole Truck Care teams (by senior manager)
#         {"reps": True}      Truck Care customers whose fuel salesperson is one of the reps in the fuel "regions" above
#   Set fuel or ttc to None to leave it out of that email.
SCOPE_BRIEFS = [
    {"id": "todd-fuel", "recipients": ["Todd Wilson"], "title": "REGIONAL FUEL EXECUTIVE SUMMARY",
     "subject": "Regional Fuel Executive Summary", "file_stem": "Regional_Fuel_Executive_Summary",
     "fuel": {"groups": ["East", "West", "Inside Sales"]}, "ttc": None},
    {"id": "todd-ttc", "recipients": ["Todd Wilson"], "title": "REGIONAL TRUCK CARE EXECUTIVE SUMMARY",
     "subject": "Regional Truck Care Executive Summary", "file_stem": "Regional_Truck_Care_Executive_Summary",
     "fuel": None, "ttc": {"teams": ["Brett Moody", "TJ Atwood"]}},
    {"id": "steve-east", "recipients": ["Steve Bennett"], "title": "EAST FLEET SALES EXECUTIVE SUMMARY",
     "subject": "East Fleet Sales Executive Summary", "file_stem": "East_Executive_Summary",
     "fuel": {"groups": ["East"]}, "ttc": {"teams": ["Brett Moody"]}},
    {"id": "quad-kevin", "recipients": ["Kevin Jernigan"], "title": "REGIONS 20, 21, 22 AND 26 WEEKLY BRIEF",
     "subject": "Regions 20, 21, 22 and 26 Weekly Brief", "file_stem": "Regions_20_21_22_26_Weekly_Brief",
     "fuel": {"regions": ["20", "21", "22", "26"]}, "ttc": {"reps": True}},
    {"id": "quad-adam", "recipients": ["Adam Troester"], "title": "REGIONS 23, 24 AND 25 WEEKLY BRIEF",
     "subject": "Regions 23, 24 and 25 Weekly Brief", "file_stem": "Regions_23_24_25_Weekly_Brief",
     "fuel": {"regions": ["23", "24", "25"]}, "ttc": {"reps": True}},
    {"id": "quad-chris", "recipients": ["Chris McGee"], "title": "REGIONS 10, 12 AND 13 WEEKLY BRIEF",
     "subject": "Regions 10, 12 and 13 Weekly Brief", "file_stem": "Regions_10_12_13_Weekly_Brief",
     "fuel": {"regions": ["10", "12", "13"]}, "ttc": {"reps": True}},
    {"id": "quad-kelvin", "recipients": ["Kelvin Ling"], "title": "REGIONS 11, 14 AND 16 WEEKLY BRIEF",
     "subject": "Regions 11, 14 and 16 Weekly Brief", "file_stem": "Regions_11_14_16_Weekly_Brief",
     "fuel": {"regions": ["11", "14", "16"]}, "ttc": {"reps": True}},
]
# Groups shown as ONE row in the executive summary's region group table (sum of the member groups).
GROUP_MERGES = {"Inside Sales": ["Inside East", "Inside West"]}
LEADERSHIP_TOP_N = 10          # rows in each executive top-N list
MANAGER_TOP_N = 10              # rows in each manager top-N list
# The weekly rep emails leave out fuel accounts that moved 30% or more in a week (a separate exception report
# covers them). True does the same for the executive top-10 fuel decreases AND increases.
EXEC_EXCLUDE_30PCT_MOVES = True
# Same 30% rule for the executive Truck Care top-10 tables. Off by default: the 30% exception report is a fuel report,
# and most Truck Care swings (small tire / PM counts) are over 30%, so turning this on empties most of those tables.
EXEC_TTC_EXCLUDE_30PCT_MOVES = False
# Regions whose accounts are left out of the executive TOP-10 LISTS only (totals and YoY tables still include them).
# Example: {"9"} to keep the aggregator programs (Region 9) out of the lists.
EXEC_LIST_EXCLUDED_REGIONS = set()

# The fleet Region report (the one behind the weekly sales-call graphs) counts these regions inside another region.
# Region 29 customers are part of Region 26 there, so the executive / manager emails do the same to match it.
REGION_ROLLUPS = {"29": "26"}

# Extra people copied on a region's weekly brief, on top of that region's Area Managers.
# Key = region number (as text), value = full names as they should be turned into First.Last@loves.com.
# Kelvin is no longer copied on Regions 11, 14 and 16: he and the other quadrant leads get their own summary instead.
EXTRA_CC = {}
