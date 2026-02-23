# 04_lab_query.py
# Query the MBTA API for Lab 1
# Design a query returning 10-20 rows and document the results
# Jonathan Lloyd

# Fetches Red Line service alerts, departures from Alewife, and arrivals to Alewife
# (near-term and future) with current stop from the Vehicles endpoint.

# 0. Setup #################################################################

## 0.1 Load Packages ######################################################

import os  # for reading environment variables
import pandas as pd  # for DataFrames
import requests  # for HTTP requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv  # for loading variables from .env

## 0.2 Load Environment ####################################################

print("Loading environment variables...")
# Load .env from script directory so it works regardless of CWD
_script_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_script_dir, ".env")
load_dotenv(_env_path)
MBTA_API_KEY = os.getenv("MBTA_API_KEY")
BASE_URL = "https://api-v3.mbta.com"
HEADERS = {"x-api-key": MBTA_API_KEY} if MBTA_API_KEY else {}
REQUEST_TIMEOUT = 15  # seconds; avoids hanging indefinitely

if MBTA_API_KEY:
    print("API key loaded from environment.")
else:
    print("No MBTA_API_KEY in .env; requests will use public access (may be rate-limited).")

# Query Plan ###############################################################
# Service Alerts: Red Line alerts (Severity, Description, Start/End Time, Active/Inactive)
# Departures: From Alewife (Destination, Scheduled/Estimated Departure, Status)
# Near-term Arrivals: To Alewife in next 10 min (Current stop, Scheduled/Estimated Arrival, Status)
# Future Arrivals: To Alewife in next 60 min (Current stop, Scheduled/Estimated Arrival, Status)


# 1. API Calls #############################################################

def get_with_timeout(url, params=None, label="request"):
    """GET with timeout and clear error messages."""
    try:
        print(f"Calling MBTA API: {label}...")
        r = requests.get(url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        print(f"  -> {label} completed (status {r.status_code}).")
        return r
    except requests.exceptions.Timeout:
        print(f"  -> {label} TIMED OUT after {REQUEST_TIMEOUT} seconds.")
        raise
    except requests.exceptions.RequestException as e:
        print(f"  -> {label} failed: {e}")
        raise

# Fetch Red Line service alerts
alerts_response = get_with_timeout(
    f"{BASE_URL}/alerts",
    params={"filter[route]": "Red"},
    label="alerts",
)
if alerts_response.status_code != 200:
    print("Alerts request failed:", alerts_response.status_code, alerts_response.text)
    exit(1)

# Fetch predictions at Alewife (departures and arrivals) with schedule, trip, stop, vehicle
predictions_response = get_with_timeout(
    f"{BASE_URL}/predictions",
    params={
        "filter[stop]": "place-alfcl",
        "filter[route]": "Red",
        "include": "schedule,trip,stop,vehicle",
    },
    label="predictions",
)
if predictions_response.status_code != 200:
    print("Predictions request failed:", predictions_response.status_code, predictions_response.text)
    exit(1)

# Fetch Red Line vehicles to get current stop per vehicle (for matching by vehicle_id)
vehicles_response = get_with_timeout(
    f"{BASE_URL}/vehicles",
    params={"filter[route]": "Red", "include": "trip,stop"},
    label="vehicles",
)
if vehicles_response.status_code != 200:
    print("Vehicles request failed:", vehicles_response.status_code, vehicles_response.text)
    exit(1)

print("All three API calls completed successfully.")

# Clear Environment ########################################################
globals().clear()
