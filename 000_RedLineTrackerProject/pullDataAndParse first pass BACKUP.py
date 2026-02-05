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


# 2. Parse Alerts ###########################################################

# Build Service Alerts DataFrame: Severity, Description, Start Time, End Time, Status
SEVERITY_MAP = {1: "Information", 2: "Warning", 3: "Emergency"}

alerts_rows = []
for item in alerts_response.json().get("data", []):
    attrs = item.get("attributes", {})
    severity_val = attrs.get("severity")
    severity_label = SEVERITY_MAP.get(severity_val, str(severity_val) if severity_val is not None else "Unknown")
    description = attrs.get("description") or attrs.get("short_header") or attrs.get("header") or ""
    active_periods = attrs.get("active_period") or []
    now = datetime.now(timezone.utc)
    status = "Inactive"
    start_time = None
    end_time = None
    if active_periods:
        first = active_periods[0]
        start_str = first.get("start")
        end_str = first.get("end")
        if start_str:
            start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        if end_str:
            end_time = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        if start_time and (end_time is None or now < end_time) and now >= start_time:
            status = "Active"
    alerts_rows.append({
        "Severity": severity_label,
        "Description": description[:200] if description else "",
        "Start Time": start_time,
        "End Time": end_time,
        "Status": status,
    })

df_alerts = pd.DataFrame(alerts_rows)


# 3. Build Included Lookup (predictions) ####################################

# JSON:API included array: resolve related resources by type and id
def build_included_lookup(included_list):
    lookup = {}
    for inc in included_list or []:
        key = (inc.get("type"), inc.get("id"))
        lookup[key] = inc
    return lookup


pred_payload = predictions_response.json()
included = build_included_lookup(pred_payload.get("included", []))
# #region agent log
def _log(location, message, data, hypothesis_id):
    import json
    with open(r"c:\Users\jonyl\iCloudDrive\Documents\GitHub\dsai\.cursor\debug.log", "a") as f:
        f.write(json.dumps({"location": location, "message": message, "data": data, "hypothesisId": hypothesis_id, "sessionId": "debug-session", "runId": "run1", "timestamp": pd.Timestamp.now().value // 10**6}) + "\n")
# #endregion
# #region agent log
_data = pred_payload.get("data", [])
_inc = pred_payload.get("included", [])
_included_types = list(set((x.get("type") for x in _inc))) if _inc else []
_sample = _data[0] if _data else {}
_log("pullDataAndParse.py:after_pred_payload", "predictions payload summary", {"data_len": len(_data), "included_len": len(_inc), "included_types": _included_types, "first_direction_id": _sample.get("attributes", {}).get("direction_id"), "first_attrs_keys": list(_sample.get("attributes", {}).keys()) if _sample else [], "first_rels_keys": list(_sample.get("relationships", {}).keys()) if _sample else []}, "H-B,H-E")
# #endregion


# 4. Parse Predictions: Departures and Arrivals #############################

def parse_iso(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def derive_status(scheduled_dt, predicted_dt, threshold_minutes=2):
    if predicted_dt is None:
        return "Cancelled"
    if scheduled_dt is None:
        return "On Time"
    delay_sec = (predicted_dt - scheduled_dt).total_seconds()
    if delay_sec <= threshold_minutes * 60:
        return "On Time"
    return "Delayed"


departures_rows = []
arrivals_rows = []
now = datetime.now(timezone.utc)
ten_min = now + timedelta(minutes=10)
sixty_min = now + timedelta(minutes=60)

_pred_idx = 0
for item in pred_payload.get("data", []):
    attrs = item.get("attributes", {})
    rels = item.get("relationships", {})
    direction_id = attrs.get("direction_id")
    if direction_id is not None and not isinstance(direction_id, int):
        direction_id = int(direction_id) if str(direction_id).isdigit() else direction_id
    pred_dep = attrs.get("departure_time")
    pred_arr = attrs.get("arrival_time")
    pred_dep_dt = parse_iso(pred_dep)
    pred_arr_dt = parse_iso(pred_arr)

    schedule_id = (rels.get("schedule") or {}).get("data")
    schedule_id = schedule_id.get("id") if isinstance(schedule_id, dict) else None
    trip_id = (rels.get("trip") or {}).get("data")
    trip_id = trip_id.get("id") if isinstance(trip_id, dict) else None
    vehicle_id = (rels.get("vehicle") or {}).get("data")
    vehicle_id = vehicle_id.get("id") if isinstance(vehicle_id, dict) else None

    schedule = included.get(("schedule", schedule_id)) if schedule_id else {}
    trip = included.get(("trip", trip_id)) if trip_id else {}
    sched_attrs = schedule.get("attributes", {})
    trip_attrs = trip.get("attributes", {})
    destination = trip_attrs.get("headsign", "")

    sched_dep = sched_attrs.get("departure_time")
    sched_arr = sched_attrs.get("arrival_time")
    sched_dep_dt = parse_iso(sched_dep)
    sched_arr_dt = parse_iso(sched_arr)

    # #region agent log
    if _pred_idx < 5:
        _log("pullDataAndParse.py:pred_loop", "per-prediction", {"idx": _pred_idx, "direction_id": direction_id, "direction_id_eq_0": direction_id == 0, "direction_id_eq_1": direction_id == 1, "pred_dep": pred_dep is not None, "pred_arr": pred_arr is not None, "schedule_id": schedule_id, "trip_id": trip_id, "schedule_key": ("schedule", schedule_id) if schedule_id else None, "trip_key": ("trip", trip_id) if trip_id else None, "schedule_in_lookup": (schedule_id and ("schedule", schedule_id) in included), "trip_in_lookup": (trip_id and ("trip", trip_id) in included)}, "H-A,H-B,H-C")
    _pred_idx += 1
    # #endregion

    # Departures from Alewife: southbound (direction_id == 1), has departure_time
    _dep_branch = direction_id == 1 and (pred_dep or sched_dep)
    if _dep_branch:
        status = derive_status(sched_dep_dt, pred_dep_dt)
        departures_rows.append({
            "Destination": destination,
            "Scheduled Departure Time": sched_dep_dt,
            "Actual Estimated Departure Time": pred_dep_dt,
            "Status": status,
        })

    # Arrivals to Alewife: northbound (direction_id == 0), has arrival_time
    _arr_branch = direction_id == 0 and (pred_arr or sched_arr)
    if _arr_branch:
        status = derive_status(sched_arr_dt, pred_arr_dt)
        arrivals_rows.append({
            "vehicle_id": vehicle_id,
            "Scheduled Arrival Time": sched_arr_dt,
            "Actual Estimated Arrival Time": pred_arr_dt,
            "Status": status,
            "arrival_time_dt": pred_arr_dt or sched_arr_dt,
        })

df_departures = pd.DataFrame(departures_rows)
if df_departures.empty:
    df_departures = pd.DataFrame(
        columns=["Destination", "Scheduled Departure Time", "Actual Estimated Departure Time", "Status"]
    )
df_arrivals_raw = pd.DataFrame(arrivals_rows)
# Ensure columns exist when there are no arrival predictions
if df_arrivals_raw.empty:
    df_arrivals_raw = pd.DataFrame(
        columns=["vehicle_id", "Scheduled Arrival Time", "Actual Estimated Arrival Time", "Status", "arrival_time_dt"]
    )


# 5. Parse Vehicles → vehicle_id to current_stop #############################

veh_payload = vehicles_response.json()
veh_included = build_included_lookup(veh_payload.get("included", []))

vehicle_to_stop = {}
for item in veh_payload.get("data", []):
    vid = item.get("id")
    stop_ref = (item.get("relationships") or {}).get("stop", {}).get("data")
    stop_id = stop_ref.get("id") if isinstance(stop_ref, dict) else None
    current_stop_name = "Unknown"
    if stop_id:
        stop_res = veh_included.get(("stop", stop_id))
        if stop_res:
            current_stop_name = (stop_res.get("attributes") or {}).get("name", stop_id)
    vehicle_to_stop[vid] = current_stop_name

# Add current stop to arrivals (match by vehicle_id)
df_arrivals_raw["Current Stop"] = df_arrivals_raw["vehicle_id"].map(
    lambda v: vehicle_to_stop.get(v, "Unknown") if pd.notna(v) else "Unknown"
)
# Filter arrivals by time window (use arrival_time_dt for comparison; NaT excluded)
arrival_dt = pd.to_datetime(df_arrivals_raw["arrival_time_dt"], utc=True)
mask_10 = (arrival_dt >= now) & (arrival_dt <= ten_min)
mask_60 = (arrival_dt >= now) & (arrival_dt <= sixty_min)
df_near_term = df_arrivals_raw.loc[mask_10, ["Current Stop", "Scheduled Arrival Time", "Actual Estimated Arrival Time", "Status"]].copy()
df_future = df_arrivals_raw.loc[mask_60, ["Current Stop", "Scheduled Arrival Time", "Actual Estimated Arrival Time", "Status"]].copy()


# 6. Document Results ######################################################

print("=" * 60)
print("SERVICE ALERTS (Red Line)")
print("=" * 60)
print(f"Number of records: {len(df_alerts)}")
print(df_alerts.to_string())
print()

print("=" * 60)
print("DEPARTURES FROM ALEWIFE")
print("=" * 60)
print(f"Number of records: {len(df_departures)}")
print(df_departures.to_string())
print()

print("=" * 60)
print("NEAR-TERM ARRIVALS TO ALEWIFE (next 10 minutes)")
print("=" * 60)
print(f"Number of records: {len(df_near_term)}")
print(df_near_term.to_string())
print()

print("=" * 60)
print("FUTURE ARRIVALS TO ALEWIFE (next 60 minutes)")
print("=" * 60)
print(f"Number of records: {len(df_future)}")
print(df_future.to_string())


# Clear Environment ########################################################
globals().clear()
