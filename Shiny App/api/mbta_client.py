# api/mbta_client.py
# MBTA V3 API client for Red Line data.
# Fetches alerts, predictions, vehicles, and shapes; returns JSON or structured error.

# 0. Setup #################################################################

import os
import requests
from pathlib import Path

from dotenv import load_dotenv

## 0.1 Load environment #####################################################

# Load .env from Shiny App folder or project root
_app_dir = Path(__file__).resolve().parent.parent
_env_paths = [_app_dir / ".env", _app_dir.parent / ".env"]
for _p in _env_paths:
    if _p.exists():
        load_dotenv(_p)
        break
else:
    load_dotenv()

BASE_URL = "https://api-v3.mbta.com"
MBTA_API_KEY = os.getenv("MBTA_API_KEY")
HEADERS = {"x-api-key": MBTA_API_KEY} if MBTA_API_KEY else {}

# 1. API helpers ############################################################


def _request(path: str, params: dict | None = None) -> dict:
    """
    GET request to MBTA API. Returns JSON body on success.
    On failure returns {"error": True, "message": "...", "status_code": int}.
    """
    if not MBTA_API_KEY:
        return {"error": True, "message": "MBTA_API_KEY is not set. Add it to .env.", "status_code": None}
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.get(url, headers=HEADERS, params=params or {}, timeout=15)
    except requests.RequestException as e:
        return {"error": True, "message": str(e), "status_code": None}
    if resp.status_code != 200:
        return {
            "error": True,
            "message": f"API request failed: status {resp.status_code}",
            "status_code": resp.status_code,
        }
    try:
        return resp.json()
    except Exception as e:
        return {"error": True, "message": f"Invalid JSON: {e}", "status_code": resp.status_code}


def fetch_alerts() -> dict:
    """Fetch Red Line service alerts. Returns JSON data or error dict."""
    return _request("/alerts", params={"filter[route]": "Red"})


def fetch_predictions() -> dict:
    """Fetch predictions at Alewife for Red Line (departures and arrivals)."""
    return _request(
        "/predictions",
        params={
            "filter[stop]": "place-alfcl",
            "filter[route]": "Red",
            "include": "schedule,trip,stop,vehicle",
        },
    )


def fetch_predictions_all_stops() -> dict:
    """Fetch predictions at all Red Line stops (for map: next station, time, delay)."""
    return _request(
        "/predictions",
        params={
            "filter[route]": "Red",
            "include": "schedule,trip,stop,vehicle",
        },
    )


def fetch_vehicles() -> dict:
    """Fetch Red Line vehicles (current stop and position for map)."""
    return _request("/vehicles", params={"filter[route]": "Red", "include": "trip,stop"})


def fetch_shapes(route_id: str = "Red") -> dict:
    """Fetch shape geometry for a route (e.g. Red Line) for map display."""
    return _request("/shapes", params={"filter[route]": route_id})


def fetch_shapes_for_routes(route_ids: list[str]) -> dict[str, dict]:
    """
    Fetch shapes for multiple routes. Returns dict mapping route_id -> shapes API response.
    Use for map layer toggles (e.g. Red, Green-B, Blue, Orange, Silver).
    """
    out = {}
    for rid in route_ids:
        out[rid] = fetch_shapes(rid)
    return out
