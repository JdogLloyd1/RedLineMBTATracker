# api/__init__.py
# MBTA API client and parsers for Red Line Shiny app.

from api.mbta_client import (
    fetch_alerts,
    fetch_predictions,
    fetch_predictions_all_stops,
    fetch_vehicles,
    fetch_shapes,
    fetch_shapes_for_routes,
)
from api.parsers import (
    parse_alerts,
    parse_departures,
    parse_near_term_arrivals,
    parse_future_arrivals,
    parse_vehicles_for_map,
    parse_vehicles_for_map_enriched,
    parse_red_line_shape,
    parse_route_shapes_merged,
    parse_merged_shapes_by_route,
)

__all__ = [
    "fetch_alerts",
    "fetch_predictions",
    "fetch_predictions_all_stops",
    "fetch_vehicles",
    "fetch_shapes",
    "fetch_shapes_for_routes",
    "parse_alerts",
    "parse_departures",
    "parse_near_term_arrivals",
    "parse_future_arrivals",
    "parse_vehicles_for_map",
    "parse_vehicles_for_map_enriched",
    "parse_red_line_shape",
    "parse_route_shapes_merged",
    "parse_merged_shapes_by_route",
]
