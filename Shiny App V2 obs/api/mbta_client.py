# api/mbta_client.py
# MBTA V3 API client for Red Line data.
# Fetches alerts, predictions (at any stop), vehicles, and shapes.

# 0. Setup #################################################################

import os
import requests
from pathlib import Path

from dotenv import load_dotenv

## 0.1 Load environment #####################################################

_app_dir = Path(__file__).resolve().parent.parent
_repo_root = _app_dir.parent
# Prefer repo-level .env so one shared file works from any run context
_env_paths = [_repo_root / ".env", _app_dir / ".env"]
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
    """GET request to MBTA API. Returns JSON body on success or error dict."""
    if not MBTA_API_KEY:
        return {"error": True, "message": "MBTA_API_KEY is not set. Add it to .env.", "status_code": None}
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.get(url, headers=HEADERS, params=params or {}, timeout=15)
    except requests.RequestException as e:
        return {"error": True, "message": str(e), "status_code": None}
    if resp.status_code != 200:
        return {"error": True, "message": f"API request failed: status {resp.status_code}", "status_code": resp.status_code}
    try:
        return resp.json()
    except Exception as e:
        return {"error": True, "message": f"Invalid JSON: {e}", "status_code": resp.status_code}


def fetch_alerts() -> dict:
    """Fetch Red Line service alerts."""
    return _request("/alerts", params={"filter[route]": "Red"})


def fetch_predictions(stop_id: str = "place-alfcl") -> dict:
    """Fetch predictions at a given stop for Red Line (departures and arrivals). Default: Alewife."""
    return _request(
        "/predictions",
        params={
            "filter[stop]": stop_id,
            "filter[route]": "Red",
            "include": "schedule,trip,stop,vehicle",
        },
    )


def fetch_predictions_at_stop(stop_id: str) -> dict:
    """Fetch predictions at a given stop for Red Line. Used for AI report (dep/arr stations)."""
    return fetch_predictions(stop_id)


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
    """Fetch shape geometry for a route for map display."""
    return _request("/shapes", params={"filter[route]": route_id})


def fetch_shapes_for_routes(route_ids: list[str]) -> dict[str, dict]:
    """Fetch shapes for multiple routes. Returns dict mapping route_id -> shapes API response."""
    out = {}
    for rid in route_ids:
        out[rid] = fetch_shapes(rid)
    return out
