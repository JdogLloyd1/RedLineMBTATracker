# api/parsers.py
# Parse MBTA API responses into DataFrames and map-ready structures.
# Ported from pullDataAndParse.py; no debug logging.

# 0. Setup #################################################################

import pandas as pd
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore

try:
    import polyline as pl
except ImportError:
    pl = None

# MBTA uses Eastern time; assume naive API times are America/New_York
MBTA_TZ = "America/New_York"

# 1. Alerts #################################################################

SEVERITY_MAP = {1: "Information", 2: "Warning", 3: "Emergency"}


def parse_alerts(alerts_response: dict) -> pd.DataFrame:
    """
    Build Service Alerts DataFrame: Severity, Description, Start Time, End Time, Status.
    Pass the JSON from fetch_alerts(). Handles empty or error response.
    """
    if alerts_response.get("error"):
        return _empty_alerts_df()
    data = alerts_response.get("data", [])
    now = datetime.now(timezone.utc)
    rows = []
    for item in data:
        attrs = item.get("attributes", {})
        severity_val = attrs.get("severity")
        severity_label = SEVERITY_MAP.get(
            severity_val, str(severity_val) if severity_val is not None else "Unknown"
        )
        description = (
            attrs.get("description")
            or attrs.get("short_header")
            or attrs.get("header")
            or ""
        )
        active_periods = attrs.get("active_period") or []
        status = "Inactive"
        start_time = None
        end_time = None
        if active_periods:
            first = active_periods[0]
            start_str = first.get("start")
            end_str = first.get("end")
            if start_str:
                start_time = _parse_iso(start_str)
            if end_str:
                end_time = _parse_iso(end_str)
            if (
                start_time
                and (end_time is None or now < end_time)
                and now >= start_time
            ):
                status = "Active"
        rows.append(
            {
                "Severity": severity_label,
                "Description": description[:200] if description else "",
                "Start Time": start_time,
                "End Time": end_time,
                "Status": status,
            }
        )
    if not rows:
        return _empty_alerts_df()
    return pd.DataFrame(rows)


def _empty_alerts_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["Severity", "Description", "Start Time", "End Time", "Status"]
    )


# 2. Predictions – included lookup ##########################################


def _build_included_lookup(included_list: list) -> dict:
    lookup = {}
    for inc in included_list or []:
        key = (inc.get("type"), inc.get("id"))
        lookup[key] = inc
    return lookup


def _parse_iso(s: str | None):
    """Parse ISO datetime string to UTC. Naive strings are treated as America/New_York."""
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None and ZoneInfo is not None:
        dt = dt.replace(tzinfo=ZoneInfo(MBTA_TZ)).astimezone(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _derive_status(scheduled_dt, predicted_dt, threshold_minutes=2):
    if predicted_dt is None:
        return "Cancelled"
    if scheduled_dt is None:
        return "On Time"
    delay_sec = (predicted_dt - scheduled_dt).total_seconds()
    if delay_sec <= threshold_minutes * 60:
        return "On Time"
    return "Delayed"


# 3. Departures and arrivals ################################################


def parse_departures(predictions_response: dict) -> pd.DataFrame:
    """
    Departures from Alewife: Destination, Scheduled/Actual Estimated Departure Time, Status.
    """
    if predictions_response.get("error"):
        return _empty_departures_df()
    payload = predictions_response
    included = _build_included_lookup(payload.get("included", []))
    departures_rows = []
    for item in payload.get("data", []):
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})
        direction_id = attrs.get("direction_id")
        if direction_id is not None and not isinstance(direction_id, int):
            direction_id = (
                int(direction_id) if str(direction_id).isdigit() else direction_id
            )
        pred_dep = attrs.get("departure_time")
        pred_arr = attrs.get("arrival_time")
        pred_dep_dt = _parse_iso(pred_dep)
        pred_arr_dt = _parse_iso(pred_arr)
        schedule_id = (rels.get("schedule") or {}).get("data")
        schedule_id = schedule_id.get("id") if isinstance(schedule_id, dict) else None
        trip_id = (rels.get("trip") or {}).get("data")
        trip_id = trip_id.get("id") if isinstance(trip_id, dict) else None
        schedule = included.get(("schedule", schedule_id)) if schedule_id else {}
        trip = included.get(("trip", trip_id)) if trip_id else {}
        sched_attrs = schedule.get("attributes", {})
        trip_attrs = trip.get("attributes", {})
        destination = trip_attrs.get("headsign", "")
        sched_dep = sched_attrs.get("departure_time") or sched_attrs.get("departure")
        sched_dep_dt = _parse_iso(sched_dep)
        if direction_id == 0 and (pred_dep or sched_dep or pred_arr):
            status = _derive_status(
                sched_dep_dt, pred_dep_dt or pred_arr_dt
            )
            dep_time = pred_dep_dt or pred_arr_dt or sched_dep_dt
            departures_rows.append(
                {
                    "Destination": destination,
                    "Scheduled Departure Time": sched_dep_dt,
                    "Actual Estimated Departure Time": pred_dep_dt or pred_arr_dt,
                    "Status": status,
                    "_sort_time": dep_time,
                }
            )
    if not departures_rows:
        return _empty_departures_df()
    df = pd.DataFrame(departures_rows)
    # Sort by departure time ascending (soonest first)
    df = df.sort_values(by="_sort_time", ascending=True, na_position="last").reset_index(drop=True)
    df = df.drop(columns=["_sort_time"])
    return df


def _empty_departures_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "Destination",
            "Scheduled Departure Time",
            "Actual Estimated Departure Time",
            "Status",
        ]
    )


def _parse_arrivals_raw(predictions_response: dict) -> pd.DataFrame:
    """Internal: arrivals with vehicle_id and arrival_time_dt for filtering."""
    if predictions_response.get("error"):
        return pd.DataFrame(
            columns=[
                "vehicle_id",
                "Scheduled Arrival Time",
                "Actual Estimated Arrival Time",
                "Status",
                "arrival_time_dt",
            ]
        )
    payload = predictions_response
    included = _build_included_lookup(payload.get("included", []))
    arrivals_rows = []
    for item in payload.get("data", []):
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})
        direction_id = attrs.get("direction_id")
        if direction_id is not None and not isinstance(direction_id, int):
            direction_id = (
                int(direction_id) if str(direction_id).isdigit() else direction_id
            )
        pred_arr = attrs.get("arrival_time")
        pred_dep = attrs.get("departure_time")
        pred_arr_dt = _parse_iso(pred_arr)
        pred_dep_dt = _parse_iso(pred_dep)
        schedule_id = (rels.get("schedule") or {}).get("data")
        schedule_id = schedule_id.get("id") if isinstance(schedule_id, dict) else None
        trip_id = (rels.get("trip") or {}).get("data")
        trip_id = trip_id.get("id") if isinstance(trip_id, dict) else None
        vehicle_id = (rels.get("vehicle") or {}).get("data")
        vehicle_id = vehicle_id.get("id") if isinstance(vehicle_id, dict) else None
        schedule = included.get(("schedule", schedule_id)) if schedule_id else {}
        sched_attrs = schedule.get("attributes", {})
        sched_arr = sched_attrs.get("arrival_time") or sched_attrs.get("arrival")
        sched_arr_dt = _parse_iso(sched_arr)
        if direction_id == 1 and (pred_arr or sched_arr or pred_dep):
            status = _derive_status(
                sched_arr_dt, pred_arr_dt or pred_dep_dt
            )
            arrivals_rows.append(
                {
                    "vehicle_id": vehicle_id,
                    "Scheduled Arrival Time": sched_arr_dt,
                    "Actual Estimated Arrival Time": pred_arr_dt or pred_dep_dt,
                    "Status": status,
                    "arrival_time_dt": pred_arr_dt or sched_arr_dt or pred_dep_dt,
                }
            )
    if not arrivals_rows:
        return pd.DataFrame(
            columns=[
                "vehicle_id",
                "Scheduled Arrival Time",
                "Actual Estimated Arrival Time",
                "Status",
                "arrival_time_dt",
            ]
        )
    return pd.DataFrame(arrivals_rows)


def _vehicle_to_stop_map(vehicles_response: dict) -> dict:
    """Build vehicle_id -> current_stop name from vehicles response."""
    if vehicles_response.get("error"):
        return {}
    payload = vehicles_response
    included = _build_included_lookup(payload.get("included", []))
    out = {}
    for item in payload.get("data", []):
        vid = item.get("id")
        stop_ref = (item.get("relationships") or {}).get("stop", {}).get("data")
        stop_id = stop_ref.get("id") if isinstance(stop_ref, dict) else None
        current_stop_name = "Unknown"
        if stop_id:
            stop_res = included.get(("stop", stop_id))
            if stop_res:
                current_stop_name = (
                    stop_res.get("attributes") or {}
                ).get("name", stop_id)
        out[vid] = current_stop_name
    return out


def parse_near_term_arrivals(
    predictions_response: dict, vehicles_response: dict
) -> pd.DataFrame:
    """Arrivals to Alewife in next 10 minutes with Current Stop."""
    raw = _parse_arrivals_raw(predictions_response)
    if raw.empty:
        return _empty_arrivals_df()
    vehicle_to_stop = _vehicle_to_stop_map(vehicles_response)
    raw["Current Stop"] = raw["vehicle_id"].map(
        lambda v: vehicle_to_stop.get(v, "Unknown") if pd.notna(v) else "Unknown"
    )
    now = datetime.now(timezone.utc)
    ten_min = now + timedelta(minutes=10)
    arrival_dt = pd.to_datetime(raw["arrival_time_dt"], utc=True)
    mask = (arrival_dt >= now) & (arrival_dt <= ten_min)
    out = raw.loc[
        mask,
        ["Current Stop", "Scheduled Arrival Time", "Actual Estimated Arrival Time", "Status"],
    ].copy()
    return out if not out.empty else _empty_arrivals_df()


def parse_future_arrivals(
    predictions_response: dict, vehicles_response: dict
) -> pd.DataFrame:
    """Arrivals to Alewife in next 60 minutes with Current Stop."""
    raw = _parse_arrivals_raw(predictions_response)
    if raw.empty:
        return _empty_arrivals_df()
    vehicle_to_stop = _vehicle_to_stop_map(vehicles_response)
    raw["Current Stop"] = raw["vehicle_id"].map(
        lambda v: vehicle_to_stop.get(v, "Unknown") if pd.notna(v) else "Unknown"
    )
    now = datetime.now(timezone.utc)
    sixty_min = now + timedelta(minutes=60)
    arrival_dt = pd.to_datetime(raw["arrival_time_dt"], utc=True)
    mask = (arrival_dt >= now) & (arrival_dt <= sixty_min)
    out = raw.loc[
        mask,
        ["Current Stop", "Scheduled Arrival Time", "Actual Estimated Arrival Time", "Status"],
    ].copy()
    return out if not out.empty else _empty_arrivals_df()


def _empty_arrivals_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "Current Stop",
            "Scheduled Arrival Time",
            "Actual Estimated Arrival Time",
            "Status",
        ]
    )


# 4. Map data – vehicles and shapes #########################################


def _next_stop_by_vehicle(predictions_response: dict) -> dict:
    """
    From predictions at all stops, for each vehicle_id return the next stop info:
    {vehicle_id: {"stop_name": str, "expected_time": datetime, "minutes_behind": float|None}}
    """
    if predictions_response.get("error"):
        return {}
    payload = predictions_response
    included = _build_included_lookup(payload.get("included", []))
    now = datetime.now(timezone.utc)
    by_vehicle = {}
    for item in payload.get("data", []):
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})
        vehicle_ref = (rels.get("vehicle") or {}).get("data")
        vehicle_id = vehicle_ref.get("id") if isinstance(vehicle_ref, dict) else None
        if not vehicle_id:
            continue
        stop_ref = (rels.get("stop") or {}).get("data")
        stop_id = stop_ref.get("id") if isinstance(stop_ref, dict) else None
        stop_name = "Unknown"
        if stop_id:
            stop_res = included.get(("stop", stop_id))
            if stop_res:
                stop_name = (stop_res.get("attributes") or {}).get("name", stop_id)
        pred_arr = attrs.get("arrival_time")
        pred_dep = attrs.get("departure_time")
        pred_dt = _parse_iso(pred_arr or pred_dep)
        if pred_dt is None or pred_dt < now:
            continue
        schedule_id = (rels.get("schedule") or {}).get("data")
        schedule_id = schedule_id.get("id") if isinstance(schedule_id, dict) else None
        schedule = included.get(("schedule", schedule_id)) if schedule_id else {}
        sched_attrs = schedule.get("attributes", {})
        sched_dt = _parse_iso(
            sched_attrs.get("arrival_time") or sched_attrs.get("arrival")
            or sched_attrs.get("departure_time")
            or sched_attrs.get("departure")
        )
        minutes_behind = None
        if sched_dt is not None and pred_dt is not None:
            minutes_behind = (pred_dt - sched_dt).total_seconds() / 60.0
        entry = {
            "stop_name": stop_name,
            "expected_time": pred_dt,
            "minutes_behind": minutes_behind,
        }
        if vehicle_id not in by_vehicle or (by_vehicle[vehicle_id]["expected_time"] > pred_dt):
            by_vehicle[vehicle_id] = entry
    return by_vehicle


def parse_vehicles_for_map_enriched(
    vehicles_response: dict,
    predictions_all_stops_response: dict | None,
) -> list[dict]:
    """
    Like parse_vehicles_for_map but with destination, direction, next_stop_name,
    next_stop_time_expected, minutes_behind for hover. Uses predictions at all stops
    when provided; otherwise falls back to basic fields only.
    """
    base_list = parse_vehicles_for_map(vehicles_response)
    if not base_list:
        return []
    next_stop = _next_stop_by_vehicle(predictions_all_stops_response or {})
    included = _build_included_lookup(vehicles_response.get("included", []) if not vehicles_response.get("error") else [])
    out = []
    for v in base_list:
        vid = v.get("vehicle_id", "")
        item = next((x for x in (vehicles_response.get("data") or []) if x.get("id") == vid), None)
        destination = "—"
        direction = "—"
        if item:
            trip_ref = (item.get("relationships") or {}).get("trip", {}).get("data")
            trip_id = trip_ref.get("id") if isinstance(trip_ref, dict) else None
            if trip_id:
                trip = included.get(("trip", trip_id))
                if trip:
                    attrs = (trip.get("attributes") or {})
                    destination = attrs.get("headsign", "—") or "—"
                    did = attrs.get("direction_id")
                    if did is not None:
                        direction = "Southbound" if did == 0 else "Northbound"
        ns = next_stop.get(vid, {})
        next_stop_name = ns.get("stop_name", "—") or "—"
        expected_time = ns.get("expected_time")
        if not expected_time:
            next_stop_time_expected = "—"
        elif ZoneInfo:
            next_stop_time_expected = expected_time.astimezone(ZoneInfo(MBTA_TZ)).strftime("%H:%M")
        else:
            next_stop_time_expected = expected_time.strftime("%H:%M")
        minutes_behind = ns.get("minutes_behind")
        if minutes_behind is not None:
            minutes_behind = round(minutes_behind, 1)
        out.append({
            **v,
            "destination": destination,
            "direction": direction,
            "next_stop_name": next_stop_name,
            "next_stop_time_expected": next_stop_time_expected,
            "minutes_behind": minutes_behind,
        })
    return out


def parse_vehicles_for_map(vehicles_response: dict) -> list[dict]:
    """
    Extract vehicle positions for map: list of {lat, lon, bearing, vehicle_id}.
    MBTA V3 Vehicle may include latitude/longitude in attributes; if not present,
    returns empty list (map can still show route from shapes).
    """
    if vehicles_response.get("error"):
        return []
    out = []
    for item in vehicles_response.get("data", []):
        attrs = item.get("attributes") or {}
        # Try direct lat/lon or nested position (GTFS-style)
        lat = attrs.get("latitude")
        if lat is None and "position" in attrs:
            pos = attrs["position"]
            if isinstance(pos, dict):
                lat = pos.get("latitude")
        lon = attrs.get("longitude")
        if lon is None and "position" in attrs:
            pos = attrs["position"]
            if isinstance(pos, dict):
                lon = pos.get("longitude")
        if lat is None or lon is None:
            continue
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            continue
        bearing = attrs.get("bearing")
        if bearing is not None:
            try:
                bearing = float(bearing)
            except (TypeError, ValueError):
                bearing = None
        out.append(
            {
                "lat": lat_f,
                "lon": lon_f,
                "bearing": bearing,
                "vehicle_id": item.get("id", ""),
            }
        )
    return out


def _decode_shape_to_lons_lats(item: dict) -> tuple[list[float], list[float]] | None:
    """Decode one shape resource to (lons, lats). Returns None if decode fails."""
    attrs = item.get("attributes") or {}
    encoded = attrs.get("polyline")
    if isinstance(encoded, str) and encoded and pl is not None:
        try:
            coords = pl.decode(encoded, precision=5)
            if coords:
                lats = [c[0] for c in coords]
                lons = [c[1] for c in coords]
                return (lons, lats)
        except Exception:
            pass
        return None
    points = attrs.get("points") or []
    if not points:
        return None
    lats = []
    lons = []
    for pt in points:
        if isinstance(pt, dict):
            la = pt.get("latitude") or pt.get("lat")
            lo = pt.get("longitude") or pt.get("lon") or pt.get("lng")
            if la is not None and lo is not None:
                lats.append(float(la))
                lons.append(float(lo))
    return (lons, lats) if lats and lons else None


def parse_red_line_shape(shapes_response: dict) -> list[tuple[list[float], list[float]]]:
    """
    Extract Red Line route geometry for map. Returns list of (lons, lats) per shape.
    MBTA returns many shapes per route; for a single merged line use parse_route_shapes_merged.
    """
    if shapes_response.get("error"):
        return []
    out = []
    for item in shapes_response.get("data", []):
        decoded = _decode_shape_to_lons_lats(item)
        if decoded:
            out.append(decoded)
    return out


def parse_route_shapes_merged(shapes_response: dict) -> tuple[list[float], list[float]] | None:
    """
    Return a single merged geometry (lons, lats) for the route by using the longest
    shape (most points). Use this so the map draws one trace per route instead of many.
    """
    shapes = parse_red_line_shape(shapes_response)
    if not shapes:
        return None
    # Use longest shape by point count
    longest = max(shapes, key=lambda s: len(s[0]))
    return longest


def parse_merged_shapes_by_route(
    responses_by_route: dict[str, dict],
) -> dict[str, tuple[list[float], list[float]]]:
    """
    Given a dict mapping route_id -> shapes API response, return a dict mapping
    route_id -> single (lons, lats) merged geometry per route.
    """
    out = {}
    for route_id, resp in responses_by_route.items():
        if resp.get("error"):
            continue
        merged = parse_route_shapes_merged(resp)
        if merged:
            out[route_id] = merged
    return out
