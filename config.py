ANTHROPIC_API_KEY = ""

FUEL_DECREASE_BUCKETS = [
    (0,  10,  "0-10% Decrease"),
    (10, 20,  "10-20% Decrease"),
    (20, 30,  "20-30% Decrease"),
]

FUEL_MAIN_THRESHOLD_GAL = 10000
NON_FUEL_ALERT_PCT = 20
CUSTOMER_DATA_START_ROW = 7
REGION_DATA_START_ROW = 6

INSIDE_SALES_REGIONS = {"30", "31", "32", "33", "34", "35", "36", "37", "39", "40", "41", "43", "44"}

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
TTC_INSIDE_MANAGER = "Brett Moody"  # "Inside" sub-team always rolls up to Brett regardless of row position

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
