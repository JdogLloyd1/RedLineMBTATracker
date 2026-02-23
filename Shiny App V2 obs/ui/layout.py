# ui/layout.py
# Split layout, station dropdowns, report panel for Shiny App V2.

from shiny import ui

# Red Line stations: stop_id -> display name (Alewife default for dep, Central for arr)
RED_LINE_STOPS = {
    "place-alfcl": "Alewife",
    "place-davis": "Davis",
    "place-portr": "Porter",
    "place-harsq": "Harvard",
    "place-cntsq": "Central",
    "place-knncl": "Kendall/MIT",
    "place-chmnl": "Charles/MGH",
    "place-pktrm": "Park Street",
    "place-dwnxg": "Downtown Crossing",
    "place-sstat": "South Station",
    "place-brdwy": "Broadway",
    "place-andrw": "Andrew",
    "place-jfk": "JFK/UMass",
}

DEFAULT_DEP_STOP = "place-alfcl"
DEFAULT_ARR_STOP = "place-cntsq"


def make_station_dropdowns():
    """Departure and arrival station select inputs."""
    choices = {k: v for k, v in RED_LINE_STOPS.items()}
    return ui.TagList(
        ui.input_select(
            "dep_station",
            "Departure station (for API & report)",
            choices=choices,
            selected=DEFAULT_DEP_STOP,
        ),
        ui.input_select(
            "arr_station",
            "Arrival station (for AI report)",
            choices=choices,
            selected=DEFAULT_ARR_STOP,
        ),
    )


def get_station_name(stop_id: str) -> str:
    """Return display name for stop_id."""
    return RED_LINE_STOPS.get(stop_id, stop_id)
