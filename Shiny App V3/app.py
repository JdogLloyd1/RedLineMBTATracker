# app.py
# MBTA Red Line Tracker V3 – Shiny for Python with AI Commuter Report
# Run: shiny run app.py (from Shiny App V3 directory)

# 0. Setup #################################################################

import asyncio
import concurrent.futures
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

from shiny import App, reactive, render, ui
import pandas as pd
import plotly.graph_objects as go
from shinywidgets import output_widget, render_widget

from math import radians, cos, sin

from api.mbta_client import (
    fetch_alerts,
    fetch_predictions_at_stop,
    fetch_predictions_all_stops,
    fetch_vehicles,
    fetch_shapes,
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
from ai_reporter.reporter import (
    build_alerts_df,
    build_predictions_df,
    build_vehicles_df,
    format_data_for_ollama_compact,
    get_report_prompt,
    query_ollama_cloud,
    write_report_docx,
)
from ui.layout import get_station_name, make_station_dropdowns

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

# Thread pool for AI report (Ollama) so UI stays responsive
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

# 1. Reactive state ########################################################

api_error = reactive.value(None)
df_alerts = reactive.value(pd.DataFrame())
df_departures = reactive.value(pd.DataFrame())
df_near_term = reactive.value(pd.DataFrame())
df_future = reactive.value(pd.DataFrame())
vehicles_map = reactive.value([])
shapes_by_route = reactive.value({})
last_api_call_time = reactive.value(None)

# Cached API responses for AI reporter (from last "Run API query")
api_cache = reactive.value(None)  # None or dict with keys: alerts, predictions_dep, predictions_arr, vehicles
# Stations (dep_stop_id, arr_stop_id) that were used to build api_cache; None if no cache
api_cache_stations = reactive.value(None)

# AI report (report text and docx filename set after task completes)
ai_report_text = reactive.value("")
ai_report_error = reactive.value("")
ai_report_docx_saved = reactive.value(None)

# 2. UI #####################################################################


def make_sidebar():
    return ui.sidebar(
        ui.input_action_button("refresh", "Run API query", class_="btn-primary"),
        ui.p(
            "Fetch Red Line data for the selected departure station: "
            "alerts, departures, arrivals, and live map. Same data is used for the AI report.",
            class_="text-muted small",
        ),
        ui.hr(),
        make_station_dropdowns(),
        ui.hr(),
        ui.input_action_button("run_ai_report", "Run AI Commuter Report", class_="btn-success"),
        ui.p("Generates a summary report via Ollama Cloud from the last API data.", class_="text-muted small"),
        ui.input_action_button("save_docx", "Save as .docx", class_="btn btn-outline-primary"),
        ui.p("Export the current report to reports/ (only enabled after generating a report).", class_="text-muted small"),
        ui.hr(),
        ui.input_slider(
            "panel_ratio",
            "Left panel width %",
            min=40,
            max=70,
            value=55,
            step=5,
        ),
        ui.hr(),
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
        title="Red Line Tracker V3",
        width=300,
    )


def make_tabs():
    return ui.div(
        ui.navset_card_tab(
            ui.nav_panel("Service Alerts", ui.output_data_frame("alerts_table"), value="alerts"),
            ui.nav_panel("Departures", ui.output_data_frame("departures_table"), value="departures"),
            ui.nav_panel("Near-term Arrivals", ui.output_data_frame("near_term_table"), value="near_term"),
            ui.nav_panel("Future Arrivals", ui.output_data_frame("future_table"), value="future"),
            ui.nav_panel(
                "Live Map",
                ui.div(output_widget("map_widget"), class_="shiny-app-v3-map-container"),
                value="map",
            ),
            id="main_tabs",
        ),
        class_="shiny-app-v3-tabs",
    )


def app_ui(request):
    return ui.page_sidebar(
        make_sidebar(),
        ui.tags.style(
            """
            .commuter-report-body table {
                border-collapse: collapse;
                width: 100%;
                margin: 0.5rem 0;
            }
            .commuter-report-body th,
            .commuter-report-body td {
                border: 1px solid #dee2e6;
                padding: 0.35rem 0.5rem;
                text-align: left;
            }
            .commuter-report-body th {
                background-color: #f8f9fa;
                font-weight: 600;
            }
            .shiny-app-v3-tabs .card-body {
                min-height: 55vh;
            }
            .shiny-app-v3-map-container {
                min-height: 55vh;
            }
            """
        ),
        ui.div(
            ui.output_ui("error_banner"),
            ui.h2("MBTA Red Line Tracker", class_="mt-3 mb-3"),
            ui.p(
                "Click 'Run API query' to load data for the selected departure station. "
                "Then use 'Run AI Commuter Report' to generate a summary.",
                class_="text-muted mb-3",
            ),
            ui.div(
                ui.output_ui("split_layout"),
                class_="flex-grow-1 d-flex flex-column min-h-0",
                style="min-height: 70vh;",
            ),
            class_="p-3 d-flex flex-column min-vh-100",
        ),
        title="Red Line Tracker V3",
        fillable=True,
    )


# 3. Server ##################################################################


def server(input, output, session):
    def _do_refresh():
        """Fetch all data for dashboard and AI reporter in one run. Uses selected dep and arr stations."""
        dep_stop = input.dep_station() or "place-alfcl"
        arr_stop = input.arr_station() or "place-cntsq"

        alerts_resp = fetch_alerts()
        predictions_dep_resp = fetch_predictions_at_stop(dep_stop)
        predictions_arr_resp = fetch_predictions_at_stop(arr_stop)
        vehicles_resp = fetch_vehicles()
        shapes_resp = fetch_shapes()

        err = None
        if alerts_resp.get("error"):
            err = alerts_resp.get("message", "API error")
        elif predictions_dep_resp.get("error"):
            err = predictions_dep_resp.get("message", "API error")
        elif vehicles_resp.get("error"):
            err = vehicles_resp.get("message", "API error")
        elif shapes_resp.get("error"):
            err = shapes_resp.get("message", "API error")
        if err:
            api_error.set(err)
            api_cache.set(None)
            api_cache_stations.set(None)
            return

        api_error.set(None)
        df_alerts.set(parse_alerts(alerts_resp))
        df_departures.set(parse_departures(predictions_dep_resp))
        df_near_term.set(parse_near_term_arrivals(predictions_dep_resp, vehicles_resp))
        df_future.set(parse_future_arrivals(predictions_dep_resp, vehicles_resp))
        vehicles_map.set(parse_vehicles_for_map(vehicles_resp))

        red_shapes = parse_red_line_shape(shapes_resp)
        current = dict(shapes_by_route())
        if red_shapes:
            current["Red"] = red_shapes
        shapes_by_route.set(current)
        last_api_call_time.set(datetime.now(EASTERN))

        predictions_all_resp = fetch_predictions_all_stops()
        if predictions_all_resp.get("error"):
            predictions_all_resp = None
        vehicles_map.set(
            parse_vehicles_for_map_enriched(vehicles_resp, predictions_all_resp)
        )

        api_cache.set({
            "alerts": alerts_resp,
            "predictions_dep": predictions_dep_resp,
            "predictions_arr": predictions_arr_resp,
            "vehicles": vehicles_resp,
        })
        api_cache_stations.set((dep_stop, arr_stop))

    @reactive.effect
    @reactive.event(input.refresh)
    def _fetch_and_parse():
        ui.notification_show("Fetching data...", duration=2, type="message")
        _do_refresh()

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

    def _run_ai_report_sync(dep_name: str, arr_name: str, cache: dict | None) -> dict:
        """Build DFs from cache, call Ollama. Returns dict with 'report' or 'error'. Runs in thread.
        Cache must be passed in; do not read reactive values inside this function (no reactive context).
        """
        if not cache:
            return {"error": "No data loaded. Click 'Run API query' first."}
        try:
            df_alerts_df = build_alerts_df(cache["alerts"])
            df_pred_dep = build_predictions_df(cache["predictions_dep"])
            df_pred_arr = build_predictions_df(cache["predictions_arr"])
            df_veh = build_vehicles_df(cache["vehicles"])
            formatted = format_data_for_ollama_compact(
                df_alerts_df, df_pred_dep, df_pred_arr, df_veh,
                dep_label=dep_name, arr_label=arr_name,
            )
            prompt = get_report_prompt(dep_name, arr_name)
            user_content = prompt + "\n\n" + formatted
            report = query_ollama_cloud(user_content)
            return {"report": report}
        except Exception as e:
            return {"error": str(e)}

    @reactive.extended_task
    async def ai_report_task(dep_name: str, arr_name: str, cache: dict | None):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            _run_ai_report_sync,
            dep_name,
            arr_name,
            cache,
        )

    @reactive.effect
    @reactive.event(input.run_ai_report)
    def _on_run_ai_report():
        dep_id = input.dep_station() or "place-alfcl"
        arr_id = input.arr_station() or "place-cntsq"
        dep_name = get_station_name(dep_id)
        arr_name = get_station_name(arr_id)
        cached_stations = api_cache_stations()
        requested = (dep_id, arr_id)
        # If cache is for different stations, refresh so report uses data for currently selected dep/arr
        if cached_stations is None or cached_stations != requested:
            ui.notification_show("Fetching data for selected stations...", duration=2, type="message")
            _do_refresh()
        cache = api_cache()
        ai_report_error.set("")
        ai_report_docx_saved.set(None)
        ai_report_text.set("")
        ui.notification_show("Generating report...", duration=None, type="message", id="ai_report_progress")
        ai_report_task.invoke(dep_name, arr_name, cache)

    @reactive.effect
    def _apply_ai_report_result():
        # Do not catch: result() raises while task is running so Shiny re-runs this effect
        # when the task completes. Catching would break the reactive dependency.
        result = ai_report_task.result()
        ui.notification_remove("ai_report_progress")
        if result.get("error"):
            ai_report_error.set(result["error"])
            ai_report_text.set("")
        else:
            ai_report_text.set(result.get("report", ""))
            ai_report_error.set("")

    @reactive.effect
    @reactive.event(input.save_docx)
    def _on_save_docx():
        txt = ai_report_text()
        if not txt:
            ui.notification_show("No report to save. Generate a report first.", type="warning", duration=3)
            return
        ui.notification_show("Saving report...", duration=None, type="message", id="save_docx_progress")
        try:
            reports_dir = Path(__file__).resolve().parent / "reports"
            out_path = write_report_docx(txt, output_dir=reports_dir)
            ai_report_docx_saved.set(out_path.name)
            ui.notification_remove("save_docx_progress")
            ui.notification_show(f"Saved: {out_path.name}", type="message", duration=3)
        except Exception as e:
            ui.notification_remove("save_docx_progress")
            ui.notification_show(f"Save failed: {e}", type="error", duration=5)

    @render.ui
    def split_layout():
        ratio = input.panel_ratio() or 55
        left_w = max(4, min(8, int(12 * ratio / 100)))
        right_w = 12 - left_w

        report_txt = ai_report_text()
        report_err = ai_report_error()
        docx_saved = ai_report_docx_saved()
        try:
            loading = ai_report_task.status() == "running"
        except Exception:
            loading = False

        if loading:
            report_content = ui.div(
                ui.h4("AI Commuter Report", class_="mb-2"),
                ui.div(ui.p("Generating report...", class_="text-muted"), class_="p-3 bg-light rounded"),
            )
        elif report_err:
            report_content = ui.div(
                ui.h4("AI Commuter Report", class_="mb-2"),
                ui.div(ui.strong("Error: "), report_err, class_="alert alert-danger", role="alert"),
            )
        elif report_txt:
            parts = [
                ui.h4("AI Commuter Report", class_="mb-2"),
                ui.div(
                    ui.markdown(report_txt),
                    class_="commuter-report-body p-3 bg-light rounded",
                    style="max-height: 60vh; overflow-y: auto;",
                ),
            ]
            if docx_saved:
                parts.insert(1, ui.p("Saved to: " + docx_saved, class_="text-success small mb-2"))
            report_content = ui.div(*parts)
        else:
            report_content = ui.div(
                ui.h4("AI Commuter Report", class_="mb-2"),
                ui.p(
                    "Click 'Run API query' to load data, then 'Run AI Commuter Report' to generate a summary.",
                    class_="text-muted",
                ),
            )

        return ui.row(
            ui.column(left_w, make_tabs(), class_="d-flex flex-column"),
            ui.column(
                right_w,
                ui.div(
                    report_content,
                    class_="border-start ps-3 h-100",
                    style="min-height: 50vh;",
                ),
                class_="d-flex flex-column",
            ),
            class_="flex-grow-1 g-3",
            style="min-height: 60vh;",
        )

    @render.ui
    def error_banner():
        err = api_error()
        if not err:
            return ui.div()
        return ui.div(
            ui.div(ui.strong("Error: "), err, class_="alert alert-danger mb-3", role="alert"),
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
            return render.DataGrid(pd.DataFrame(), width="100%", height="38vh")
        return render.DataGrid(
            _format_df_for_display(df, ["Start Time", "End Time"]),
            width="100%",
            height="38vh",
        )

    @render.data_frame
    def departures_table():
        df = df_departures()
        if df.empty:
            return render.DataGrid(pd.DataFrame(), width="100%", height="38vh")
        return render.DataGrid(
            _format_df_for_display(
                df,
                ["Scheduled Departure Time", "Actual Estimated Departure Time"],
            ),
            width="100%",
            height="38vh",
        )

    @render.data_frame
    def near_term_table():
        df = df_near_term()
        if df.empty:
            return render.DataGrid(pd.DataFrame(), width="100%", height="38vh")
        return render.DataGrid(
            _format_df_for_display(
                df,
                ["Scheduled Arrival Time", "Actual Estimated Arrival Time"],
            ),
            width="100%",
            height="38vh",
        )

    @render.data_frame
    def future_table():
        df = df_future()
        if df.empty:
            return render.DataGrid(pd.DataFrame(), width="100%", height="38vh")
        return render.DataGrid(
            _format_df_for_display(
                df,
                ["Scheduled Arrival Time", "Actual Estimated Arrival Time"],
            ),
            width="100%",
            height="38vh",
        )

    @render_widget
    def map_widget():
        vehicles = vehicles_map()
        cache = shapes_by_route()
        selected = list(input.map_routes() or ["Red"])
        center_lat = 42.373
        center_lon = -71.118
        fig = go.Figure()
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
            height=600,
        )
        widget = go.FigureWidget(fig.data, fig.layout)
        widget._config["scrollZoom"] = True
        return widget


# 4. Run ####################################################################

app = App(app_ui, server)
app.on_shutdown(_executor.shutdown)

if __name__ == "__main__":
    from shiny import run_app
    run_app(app)
