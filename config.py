ANTHROPIC_API_KEY = "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"

FUEL_DECREASE_BUCKETS = [
    (0,  10,  "0-10% Decrease"),
    (10, 20,  "10-20% Decrease"),
    (20, 30,  "20-30% Decrease"),
]

FUEL_MAIN_THRESHOLD_GAL = 10000
NON_FUEL_ALERT_PCT = 20
CUSTOMER_DATA_START_ROW = 7
REGION_DATA_START_ROW = 7

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