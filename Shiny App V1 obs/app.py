# app.py
# MBTA Red Line Tracker – Shiny for Python
# Run: shiny run app.py (from Shiny App directory)

# 0. Setup #################################################################

from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

from shiny import App, reactive, render, ui
import pandas as pd
import plotly.graph_objects as go
from shinywidgets import output_widget, render_widget

from math import radians, cos, sin

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
)

# Map layer choices: display name -> list of MBTA route IDs (one or more for branches)
MAP_ROUTE_IDS = {
    "Red": ["Red"],
    "Green": ["Green-B", "Green-C", "Green-D", "Green-E"],
    "Blue": ["Blue"],
    "Orange": ["Orange"],
    "Silver": ["Silver"],
}
MAP_COLORS = {
    "Red": "#DA291C",
    "Green": "#00843D",
    "Blue": "#003DA5",
    "Orange": "#ED8B00",
    "Silver": "#7C8793",
}

# 1. Reactive state ########################################################

api_error = reactive.value(None)
df_alerts = reactive.value(pd.DataFrame())
df_departures = reactive.value(pd.DataFrame())
df_near_term = reactive.value(pd.DataFrame())
df_future = reactive.value(pd.DataFrame())
vehicles_map = reactive.value([])
# Merged (lons, lats) per display route name; Red set on refresh, others on first toggle
shapes_by_route = reactive.value({})
# Time of last successful API refresh (for sidebar display)
last_api_call_time = reactive.value(None)
# When True, next timer run only reschedules (avoids double refresh on manual Run API query)
skip_next_timer_refresh = reactive.value(False)

# Minimum auto-refresh interval (minutes) to avoid UI freezing from overlapping refreshes
MIN_AUTO_REFRESH_MINUTES = 0.5

# 2. UI #####################################################################


def make_sidebar():
    return ui.sidebar(
        ui.input_action_button("refresh", "Run API query", class_="btn-primary"),
        ui.p(
            "Click to fetch the latest Red Line data from the MBTA API: "
            "service alerts, Alewife departures and arrivals, and live map."
        ),
        ui.hr(),
        ui.input_numeric(
            "refresh_interval_min",
            "Auto-refresh (minutes)",
            value=0,
            min=0,
            step=0.1,
        ),
        ui.p(
            "0 = off. When > 0, data refreshes automatically (e.g. 0.5 = 30 sec; min 0.5 to avoid freezing).",
            class_="text-muted small",
        ),
        ui.output_ui("last_api_call_ui"),
        ui.hr(),
        ui.input_checkbox_group(
            "map_routes",
            "Map layers",
            choices={
                "Red": "Red Line",
                "Green": "Green Line",
                "Blue": "Blue Line",
                "Orange": "Orange Line",
                "Silver": "Silver Line",
            },
            selected=["Red"],
        ),
        ui.hr(),
        ui.p(
            "Data includes: Service Alerts, Departures from Alewife, "
            "Near-term Arrivals (10 min), Future Arrivals (60 min), and Live Map.",
            class_="text-muted small",
        ),
        title="Red Line Tracker",
        width=280,
    )


def make_tabs():
    return ui.navset_card_tab(
        ui.nav_panel(
            "Service Alerts",
            ui.output_data_frame("alerts_table"),
            value="alerts",
        ),
        ui.nav_panel(
            "Departures",
            ui.output_data_frame("departures_table"),
            value="departures",
        ),
        ui.nav_panel(
            "Near-term Arrivals",
            ui.output_data_frame("near_term_table"),
            value="near_term",
        ),
        ui.nav_panel(
            "Future Arrivals",
            ui.output_data_frame("future_table"),
            value="future",
        ),
        ui.nav_panel(
            "Live Map",
            output_widget("map_widget"),
            value="map",
        ),
        id="main_tabs",
    )


def app_ui(request):
    return ui.page_sidebar(
        make_sidebar(),
        ui.div(
            ui.output_ui("error_banner"),
            ui.h2("MBTA Red Line – Alewife", class_="mt-3 mb-3"),
            ui.p(
                "Click 'Run API query' in the sidebar to load the latest data.",
                class_="text-muted mb-3",
            ),
            make_tabs(),
            class_="p-3",
        ),
        title="Red Line Tracker",
        fillable=True,
    )


# 3. Server ##################################################################


def server(input, output, session):
    def _do_refresh():
        """Shared refresh: fetch API, parse, update reactive values. Updates UI quickly after main calls; enrichment (predictions all stops) runs after."""
        alerts_resp = fetch_alerts()
        predictions_resp = fetch_predictions()
        vehicles_resp = fetch_vehicles()
        shapes_resp = fetch_shapes()
        err = None
        if alerts_resp.get("error"):
            err = alerts_resp.get("message", "API error")
        elif predictions_resp.get("error"):
            err = predictions_resp.get("message", "API error")
        elif vehicles_resp.get("error"):
            err = vehicles_resp.get("message", "API error")
        elif shapes_resp.get("error"):
            err = shapes_resp.get("message", "API error")
        if err:
            api_error.set(err)
            return
        api_error.set(None)
        df_alerts.set(parse_alerts(alerts_resp))
        df_departures.set(parse_departures(predictions_resp))
        df_near_term.set(
            parse_near_term_arrivals(predictions_resp, vehicles_resp)
        )
        df_future.set(
            parse_future_arrivals(predictions_resp, vehicles_resp)
        )
        # Show trains on map immediately (basic positions)
        vehicles_map.set(parse_vehicles_for_map(vehicles_resp))
        red_shapes = parse_red_line_shape(shapes_resp)
        current = dict(shapes_by_route())
        if red_shapes:
            current["Red"] = red_shapes
        shapes_by_route.set(current)
        last_api_call_time.set(datetime.now(EASTERN))
        # Enrich map with predictions at all stops (hover, next station); can be slow
        predictions_all_resp = fetch_predictions_all_stops()
        if predictions_all_resp.get("error"):
            predictions_all_resp = None
        vehicles_map.set(
            parse_vehicles_for_map_enriched(vehicles_resp, predictions_all_resp)
        )

    @reactive.effect
    @reactive.event(input.refresh)
    def _fetch_and_parse():
        skip_next_timer_refresh.set(True)  # Reset auto-refresh timer without double fetch
        _do_refresh()

    @reactive.effect
    def _auto_refresh_timer():
        input.refresh()  # Re-run when user clicks Run API query (reset timer)
        interval_min = input.refresh_interval_min()
        if interval_min is None or interval_min <= 0:
            return
        # Enforce minimum interval so short values (e.g. 0.1 min) don't freeze the app
        delay_sec = max(float(interval_min), MIN_AUTO_REFRESH_MINUTES) * 60
        if skip_next_timer_refresh():
            skip_next_timer_refresh.set(False)
            reactive.invalidate_later(delay_sec)
            return
        _do_refresh()
        reactive.invalidate_later(delay_sec)

    # Fetch shapes for other map layers when first selected (all branches per route)
    @reactive.effect
    def _fetch_extra_map_layers():
        selected = list(input.map_routes() or [])
        cache = dict(shapes_by_route())
        to_fetch = [r for r in selected if r not in cache and r in MAP_ROUTE_IDS]
        if not to_fetch:
            return
        for name in to_fetch:
            ids = MAP_ROUTE_IDS[name]
            all_geoms = []
            for rid in ids:
                resp = fetch_shapes(rid) if rid else None
                if resp and not resp.get("error"):
                    all_geoms.extend(parse_red_line_shape(resp))
            if all_geoms:
                cache[name] = all_geoms
        shapes_by_route.set(cache)

    @render.ui
    def error_banner():
        err = api_error()
        if not err:
            return ui.div()
        return ui.div(
            ui.div(
                ui.strong("Error: "),
                err,
                class_="alert alert-danger mb-3",
                role="alert",
            )
        )

    @render.ui
    def last_api_call_ui():
        t = last_api_call_time()
        if t is None:
            return ui.p("Last API call: —", class_="text-muted small")
        if t.tzinfo is None:
            t = t.replace(tzinfo=EASTERN)
        else:
            t = t.astimezone(EASTERN)
        return ui.p(
            "Last API call: " + t.strftime("%Y-%m-%d %H:%M:%S %Z"),
            class_="text-muted small",
        )

    def _format_df_for_display(df, datetime_cols=None):
        """Copy df and format datetime columns for display in Eastern time."""
        datetime_cols = datetime_cols or []
        out = df.copy()
        for col in datetime_cols:
            if col in out.columns:
                out[col] = (
                    pd.to_datetime(out[col], utc=True)
                    .dt.tz_convert("America/New_York")
                    .dt.strftime("%Y-%m-%d %H:%M")
                )
        return out

    @render.data_frame
    def alerts_table():
        df = df_alerts()
        if df.empty:
            return render.DataGrid(pd.DataFrame(), width="100%", height="400px")
        return render.DataGrid(
            _format_df_for_display(df, ["Start Time", "End Time"]),
            width="100%",
            height="400px",
        )

    @render.data_frame
    def departures_table():
        df = df_departures()
        if df.empty:
            return render.DataGrid(pd.DataFrame(), width="100%", height="400px")
        return render.DataGrid(
            _format_df_for_display(
                df,
                ["Scheduled Departure Time", "Actual Estimated Departure Time"],
            ),
            width="100%",
            height="400px",
        )

    @render.data_frame
    def near_term_table():
        df = df_near_term()
        if df.empty:
            return render.DataGrid(pd.DataFrame(), width="100%", height="400px")
        return render.DataGrid(
            _format_df_for_display(
                df,
                ["Scheduled Arrival Time", "Actual Estimated Arrival Time"],
            ),
            width="100%",
            height="400px",
        )

    @render.data_frame
    def future_table():
        df = df_future()
        if df.empty:
            return render.DataGrid(pd.DataFrame(), width="100%", height="400px")
        return render.DataGrid(
            _format_df_for_display(
                df,
                ["Scheduled Arrival Time", "Actual Estimated Arrival Time"],
            ),
            width="100%",
            height="400px",
        )

    @render_widget
    def map_widget():
        vehicles = vehicles_map()
        cache = shapes_by_route()
        selected = list(input.map_routes() or ["Red"])
        center_lat = 42.373
        center_lon = -71.118
        fig = go.Figure()
        # All branches per route: each route has a list of (lons, lats) geometries
        for name in selected:
            if name not in cache:
                continue
            geoms = cache[name]
            if not isinstance(geoms, list):
                geoms = [geoms]
            color = MAP_COLORS.get(name, "#333333")
            label = f"{name} Line" if name != "Green" else "Green Line"
            for lons, lats in geoms:
                fig.add_trace(
                    go.Scattermapbox(
                        lon=lons,
                        lat=lats,
                        mode="lines",
                        line=dict(width=4, color=color),
                        name=label,
                        showlegend=False,
                    )
                )
        if vehicles:
            lats = [v["lat"] for v in vehicles]
            lons = [v["lon"] for v in vehicles]
            customdata = [
                [
                    v.get("vehicle_id", "—"),
                    v.get("direction", "—"),
                    v.get("destination", "—"),
                    v.get("next_stop_name", "—"),
                    v.get("next_stop_time_expected", "—"),
                    v.get("minutes_behind") if v.get("minutes_behind") is not None else "—",
                ]
                for v in vehicles
            ]
            hovertemplate = (
                "<b>Train ID</b>: %{customdata[0]}<br>"
                "<b>Direction</b>: %{customdata[1]}<br>"
                "<b>Destination</b>: %{customdata[2]}<br>"
                "<b>Next station</b>: %{customdata[3]}<br>"
                "<b>Expected at next</b>: %{customdata[4]}<br>"
                "<b>Minutes behind</b>: %{customdata[5]}<extra></extra>"
            )
            # Single train legend entry: circle (hover) + direction line (no legend)
            fig.add_trace(
                go.Scattermapbox(
                    lon=lons,
                    lat=lats,
                    mode="markers",
                    marker=dict(size=14, color="#FFC72C", symbol="circle"),
                    name="Trains",
                    legendgroup="Trains",
                    customdata=customdata,
                    hovertemplate=hovertemplate,
                )
            )
            # Direction: short line from each train in bearing direction (same color, part of icon)
            arrow_lats, arrow_lons = [], []
            for v in vehicles:
                lat, lon = v["lat"], v["lon"]
                bearing = v.get("bearing")
                if bearing is not None:
                    br = radians(float(bearing))
                    k = 0.0004
                    dlat = k * cos(br)
                    dlon = k * sin(br) / max(cos(radians(lat)), 0.01)
                    arrow_lats.extend([lat, lat + dlat, None])
                    arrow_lons.extend([lon, lon + dlon, None])
            if arrow_lons:
                fig.add_trace(
                    go.Scattermapbox(
                        lon=arrow_lons,
                        lat=arrow_lats,
                        mode="lines",
                        line=dict(width=4, color="#FFC72C"),
                        name="Trains",
                        legendgroup="Trains",
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )
        fig.update_layout(
            mapbox=dict(
                style="open-street-map",
                center=dict(lat=center_lat, lon=center_lon),
                zoom=10,
            ),
            margin=dict(l=0, r=0, t=24, b=0),
            showlegend=True,
            height=700,
        )
        # Return as FigureWidget with scroll zoom enabled for the map
        widget = go.FigureWidget(fig.data, fig.layout)
        widget._config["scrollZoom"] = True
        return widget


# 4. Run ####################################################################

app = App(app_ui, server)

if __name__ == "__main__":
    from shiny import run_app
    run_app(app)
