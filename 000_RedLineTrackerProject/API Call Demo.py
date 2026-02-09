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

load_dotenv(".env")
MBTA_API_KEY = os.getenv("MBTA_API_KEY")
BASE_URL = "https://api-v3.mbta.com"
HEADERS = {"x-api-key": MBTA_API_KEY} if MBTA_API_KEY else {}

# Query Plan ###############################################################
# Service Alerts: Red Line alerts (Severity, Description, Start/End Time, Active/Inactive)
# Departures: From Alewife (Destination, Scheduled/Estimated Departure, Status)
# Near-term Arrivals: To Alewife in next 10 min (Current stop, Scheduled/Estimated Arrival, Status)
# Future Arrivals: To Alewife in next 60 min (Current stop, Scheduled/Estimated Arrival, Status)


# 1. API Calls #############################################################

# Fetch Red Line service alerts
alerts_response = requests.get(
    f"{BASE_URL}/alerts",
    headers=HEADERS,
    params={"filter[route]": "Red"},
)
if alerts_response.status_code != 200:
    print("Alerts request failed:", alerts_response.status_code, alerts_response.text)
    exit(1)

# Fetch predictions at Alewife (departures and arrivals) with schedule, trip, stop, vehicle
predictions_response = requests.get(
    f"{BASE_URL}/predictions",
    headers=HEADERS,
    params={
        "filter[stop]": "place-alfcl",
        "filter[route]": "Red",
        "include": "schedule,trip,stop,vehicle",
    },
)
if predictions_response.status_code != 200:
    print("Predictions request failed:", predictions_response.status_code, predictions_response.text)
    exit(1)

# Fetch Red Line vehicles to get current stop per vehicle (for matching by vehicle_id)
vehicles_response = requests.get(
    f"{BASE_URL}/vehicles",
    headers=HEADERS,
    params={"filter[route]": "Red", "include": "trip,stop"},
)
if vehicles_response.status_code != 200:
    print("Vehicles request failed:", vehicles_response.status_code, vehicles_response.text)
    exit(1)


# Clear Environment ########################################################
globals().clear()
