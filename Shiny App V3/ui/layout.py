# ui/layout.py
# Station dropdowns and layout helpers for Shiny App V3.

from shiny import ui

# Red Line stations: stop_id -> display name (Alewife default for dep, Central for arr)
# North to south; after JFK/UMass: Ashmont branch then Braintree branch
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
    "place-smmnl": "Savin Hill",
    "place-fldcr": "Fields Corner",
    "place-sbmut": "Shawmut",
    "place-asmnl": "Ashmont",
    "place-nqncy": "North Quincy",
    "place-wlsta": "Wollaston",
    "place-qnctr": "Quincy Center",
    "place-qamnl": "Quincy Adams",
    "place-brntn": "Braintree",
}

# Grouped choices for dropdowns: optgroup label -> {stop_id: display name}
# Top-level keys are non-selectable dividers in the select.
RED_LINE_STOPS_GROUPED = {
    "Alewife → JFK/UMass": {
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
    },
    "Ashmont branch": {
        "place-smmnl": "Savin Hill",
        "place-fldcr": "Fields Corner",
        "place-sbmut": "Shawmut",
        "place-asmnl": "Ashmont",
    },
    "Braintree branch": {
        "place-nqncy": "North Quincy",
        "place-wlsta": "Wollaston",
        "place-qnctr": "Quincy Center",
        "place-qamnl": "Quincy Adams",
        "place-brntn": "Braintree",
    },
}

DEFAULT_DEP_STOP = "place-alfcl"
DEFAULT_ARR_STOP = "place-cntsq"


def make_station_dropdowns():
    """Departure and arrival station select inputs with grouped options (Ashmont/Braintree)."""
    return ui.TagList(
        ui.input_select(
            "dep_station",
            "Departure station (dashboard & report)",
            choices=RED_LINE_STOPS_GROUPED,
            selected=DEFAULT_DEP_STOP,
        ),
        ui.input_select(
            "arr_station",
            "Arrival station (for AI report)",
            choices=RED_LINE_STOPS_GROUPED,
            selected=DEFAULT_ARR_STOP,
        ),
    )


def get_station_name(stop_id: str) -> str:
    """Return display name for stop_id."""
    return RED_LINE_STOPS.get(stop_id, stop_id)
