# Alewife Red Line Query Implementation Plan (Updated)

## Scope (from [04_lab_query.py](01_query_api/04_lab_query.py) lines 19–46)

1. **Service Alerts** – Red Line alerts: Severity, Description, Start Time, End Time, Status (Active/Inactive).
2. **Departures** – From Alewife: Destination, Scheduled/Estimated Departure Time, Status (On Time/Delayed/Cancelled).
3. **Near-term Arrivals** – To Alewife in next 10 min: **Current stop**, Scheduled/Estimated Arrival Time, Status.
4. **Future Arrivals** – To Alewife in next 60 min: **Current stop**, Scheduled/Estimated Arrival Time, Status.

---

## 1. Service Alerts for the Red Line

**Endpoint:** `GET /alerts`

**Purpose:** Red Line service alerts with severity, description, active period, and active status.

**Implementation:**

- **Request:**  
  - URL: `https://api-v3.mbta.com/alerts`  
  - Query params: `filter[route]=Red`. Optionally `filter[activity]` if you only want certain activity types.  
  - Headers: `x-api-key: MBTA_API_KEY`  
- **Parse response (JSON:API):**
  - For each alert in `data`: read `attributes`:
    - **Severity** – e.g. `severity` (values like 1 = Information, 2 = Warning, 3 = Emergency; confirm in [Swagger](https://api-v3.mbta.com/docs/swagger/index.html#/Alert)).
    - **Description** – e.g. `description` or `short_header` / `header` (use what the API provides for “description”).
    - **Start Time / End Time** – from `active_period`: array of `{ start: "ISO8601", end: "ISO8601" }`; use first (or current) period for Start Time and End Time.
    - **Status (Active/Inactive)** – derive from `active_period`: if current time is within any `start`–`end` then Active, else Inactive (and optionally omit inactive if you only want “upcoming”/active).
- **Output:** A table or DataFrame with columns: Severity, Description, Start Time, End Time, Status.

**Note:** If the API returns only active alerts by default, “Upcoming” may mean “currently active”; if you need future-dated but not yet active alerts, use active_period to filter and label status.

---

## 2. Departures from Alewife

**Endpoint:** `GET /predictions`

**Purpose:** Upcoming departures from Alewife with destination, scheduled vs estimated departure time, and status.

**Implementation:**

- **Request:**  
  - URL: `https://api-v3.mbta.com/predictions`  
  - Params: `filter[stop]=place-alfcl`, `filter[route]=Red`, `include=schedule,trip,stop`  
- **Parse:** For each prediction where `direction_id == 0` (southbound = departures from Alewife, per MBTA/GTFS) and the prediction has a **departure_time** at Alewife:
  - **Destination:** from included `trip` → `headsign`.
  - **Scheduled departure:** from included `schedule` (match by prediction’s `relationships.schedule`) → `departure_time`.
  - **Actual estimated departure:** prediction’s `departure_time`.
  - **Status:** On Time / Delayed / Cancelled – compare scheduled vs predicted time; if no prediction or cancelled flag, use Cancelled.
- **Output:** Table/DataFrame: Destination, Scheduled Departure Time, Actual Estimated Departure Time, Status.

---

## 3. Current Stop for Incoming Trains (Option A: Vehicles Endpoint + Match by Vehicle ID)

**Requirement:** For each train **arriving at Alewife**, show its **current stop** (the stop the train is at or most recently left).

**Approach (Option A):** Use the **Vehicles** endpoint to get each Red Line vehicle’s current stop, then **match that stop data to the arrivals dataframe by vehicle ID**.

**Implementation:**

1. **Predictions (arrivals at Alewife):**  
   - Call **`GET /predictions`** with `filter[stop]=place-alfcl`, `filter[route]=Red`, `include=schedule,trip,stop,vehicle`.  
   - For each **arrival** prediction (`direction_id == 1`, northbound, use `arrival_time`), capture the **vehicle ID** from `relationships.vehicle.data.id` (and resolve from `included` if present).  
   - Build the arrivals dataframe with: trip/headsign, scheduled/estimated arrival time, status, and **vehicle_id** (so we can join later).

2. **Vehicles (current stop):**  
   - Call **`GET /vehicles`** with `filter[route]=Red`, `include=trip,stop`.  
   - For each vehicle in `data`, read:
     - **Vehicle ID** from `id` (or `data.id`).
     - **Current stop** from the related **stop** in `included` (resolve via `relationships.stop.data.id`). From that stop resource, use the stop **name** (e.g. `attributes.name`) or stop ID as “current stop”.  
   - Build a mapping: **vehicle_id → current_stop** (e.g. a dict or a small DataFrame with columns `vehicle_id`, `current_stop`).

3. **Match by vehicle ID:**  
   - Join the **arrivals dataframe** (from predictions) with the **vehicle_id → current_stop** mapping on **vehicle_id**.  
   - Each row in the arrivals table (Near-term and Future Arrivals) now has a **Current stop** column populated from the Vehicles response.  
   - If a prediction has no vehicle (e.g. vehicle relationship missing), leave Current stop blank or “Unknown”.

**Summary:** Predictions supply arrival times and vehicle IDs; Vehicles supply current stop per vehicle ID; match by vehicle ID to attach current stop to each incoming train row.

---

## 4. Near-term Arrivals (Next 10 Minutes)

**Endpoint:** `GET /predictions` (with `include=schedule,trip,stop,vehicle`); **`GET /vehicles`** for current stop (see §3).

**Implementation:**

- From predictions: keep **arrivals at Alewife** (`direction_id == 1`, northbound), filter where **arrival_time** is in [now, now + 10 minutes]. Build a dataframe with vehicle_id, scheduled/estimated arrival time, status.
- Use the **vehicle_id → current_stop** mapping from the Vehicles endpoint (§3) to add **Current stop** to each row (match by vehicle_id).
- **Output:** Table/DataFrame: Current Stop, Scheduled Arrival Time, Actual Estimated Arrival Time, Status.

---

## 5. Future Arrivals Outlook (Next 60 Minutes)

Same as §4, but filter **arrival_time** in [now, now + 60 minutes]. Same columns: Current Stop, Scheduled Arrival Time, Actual Estimated Arrival Time, Status. Current stop again comes from the Vehicles endpoint and match by vehicle ID (§3).

---

## 6. Tasking Summary

| # | Task | Endpoint(s) | Output |
|---|------|-------------|--------|
| 1 | Fetch and parse Red Line alerts | `GET /alerts?filter[route]=Red` | Severity, Description, Start Time, End Time, Status (Active/Inactive) |
| 2 | Fetch predictions at Alewife (departures + arrivals) | `GET /predictions?filter[stop]=place-alfcl&filter[route]=Red&include=schedule,trip,stop,vehicle` | Base data for departures and arrivals; **vehicle_id** per prediction |
| 3 | Fetch Red Line vehicles and current stop | `GET /vehicles?filter[route]=Red&include=trip,stop` | **vehicle_id → current_stop** mapping (resolve stop name from included) |
| 4 | Match current stop to arrivals by vehicle ID | In code | Join arrivals dataframe with vehicle_id → current_stop on **vehicle_id** |
| 5 | Build Departures table | From predictions (direction_id=0, southbound, departure_time) | Destination, Scheduled/Estimated Departure, Status |
| 6 | Build Near-term Arrivals table | From predictions (direction_id=1, northbound, arrival in 10 min) + **current stop from Vehicles match by vehicle_id** | Current Stop, Scheduled/Estimated Arrival, Status |
| 7 | Build Future Arrivals table | From predictions (direction_id=1, northbound, arrival in 60 min) + **current stop from Vehicles match by vehicle_id** | Same columns as near-term |
| 8 | Derive Status for departures/arrivals | In code | Compare scheduled vs predicted; handle missing/cancelled |
| 9 | Document results | — | Print or display the four outputs: Alerts, Departures, Near-term Arrivals, Future Arrivals |

---

## 7. Files to Update

- **[01_query_api/04_lab_query.py](01_query_api/04_lab_query.py)**  
  - **Query Implementation:**  
    - One `GET /alerts?filter[route]=Red`.  
    - One `GET /predictions?filter[stop]=place-alfcl&filter[route]=Red&include=schedule,trip,stop,vehicle`.  
    - One `GET /vehicles?filter[route]=Red&include=trip,stop` (to get current stop per vehicle).  
  - Parse alerts; parse predictions and included (schedule, trip, stop, vehicle); **parse vehicles and build vehicle_id → current_stop**; **match current stop to arrivals dataframe by vehicle_id**.  
  - Split predictions into: departures (direction_id=0, southbound), near-term arrivals (direction_id=1, northbound, arrival in 10 min), future arrivals (arrival in 60 min).  
  - Derive Status (On Time/Delayed/Cancelled) for departures and arrivals.  
  - Output four datasets: Service Alerts, Departures, Near-term Arrivals (with Current stop from Vehicles), Future Arrivals (with Current stop from Vehicles).

---

## 8. Reference

- Alewife stop ID: **`place-alfcl`**.  
- Red Line at Alewife: southbound = departures (`direction_id=0`), northbound = arrivals (`direction_id=1`) per MBTA/GTFS.  
- Alerts: [Swagger – Alert](https://api-v3.mbta.com/docs/swagger/index.html#/Alert).  
- Predictions: [Swagger – Prediction](https://api-v3.mbta.com/docs/swagger/index.html#/Prediction).  
- Vehicles: [Swagger – Vehicle](https://api-v3.mbta.com/docs/swagger/index.html#/Vehicle/ApiWeb_VehicleController_index).
