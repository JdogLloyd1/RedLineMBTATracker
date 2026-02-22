# app.py
# MBTA Red Line Tracker V2 – Shiny for Python with AI Commuter Report
# Run: shiny run app.py (from Shiny App V2 directory)

# 0. Setup #################################################################

import asyncio
import concurrent.futures
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

from shiny import App, reactive, render, ui
from shiny.types import SilentException
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
    fetch_predictions_at_stop,
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

# Map layer choices
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

# Thread pool for running sync I/O (API calls) in background
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# 1. Reactive state ########################################################

api_error = reactive.value(None)
df_alerts = reactive.value(pd.DataFrame())
df_departures = reactive.value(pd.DataFrame())
df_near_term = reactive.value(pd.DataFrame())
df_future = reactive.value(pd.DataFrame())
vehicles_map = reactive.value([])
shapes_by_route = reactive.value({})
last_api_call_time = reactive.value(None)
skip_next_timer_refresh = reactive.value(False)
# AI report: text and error
ai_report_text = reactive.value("")
ai_report_error = reactive.value("")

MIN_AUTO_REFRESH_MINUTES = 0.5

# 2. UI #####################################################################


def make_sidebar():
    return ui.sidebar(
        ui.input_action_button("refresh", "Run API query", class_="btn-primary"),
        ui.p(
            "Fetch Red Line data for the selected departure station: "
            "alerts, departures, arrivals, and live map.",
            class_="text-muted small",
        ),
        ui.hr(),
        make_station_dropdowns(),
        ui.hr(),
        ui.input_action_button("run_ai_report", "Run AI Commuter Report", class_="btn-success"),
        ui.p(
            "Generates a summary report via Ollama Cloud and saves .docx to reports/.",
            class_="text-muted small",
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
            "0 = off. When > 0, data refreshes automatically.",
            class_="text-muted small",
        ),
        ui.input_numeric(
            "map_height",
            "Map height (px)",
            value=700,
            min=400,
            max=900,
            step=50,
        ),
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
        title="Red Line Tracker V2",
        width=300,
    )


def make_tabs():
    return ui.navset_card_tab(
        ui.nav_panel("Service Alerts", ui.output_data_frame("alerts_table"), value="alerts"),
        ui.nav_panel("Departures", ui.output_data_frame("departures_table"), value="departures"),
        ui.nav_panel("Near-term Arrivals", ui.output_data_frame("near_term_table"), value="near_term"),
        ui.nav_panel("Future Arrivals", ui.output_data_frame("future_table"), value="future"),
        ui.nav_panel("Live Map", output_widget("map_widget"), value="map"),
        id="main_tabs",
    )


def app_ui(request):
    return ui.page_sidebar(
        make_sidebar(),
        ui.div(
            ui.output_ui("error_banner"),
            ui.h2("MBTA Red Line – Alewife", class_="mt-3 mb-3"),
            ui.p(
                "Click 'Run API query' to load data. Use station dropdowns to change departure/arrival. "
                "Click 'Run AI Commuter Report' to generate a summary.",
                class_="text-muted mb-3",
            ),
            ui.output_ui("split_layout"),
            class_="p-3",
        ),
        title="Red Line Tracker V2",
        fillable=True,
    )


# 2.5 Sync worker functions (run in thread pool, no reactive access) #########


def _do_refresh_sync(dep_stop: str) -> dict:
    """Fetch and parse MBTA data. Returns dict with data or error. Runs in thread."""
    dep_stop = dep_stop or "place-alfcl"
    alerts_resp = fetch_alerts()
    predictions_resp = fetch_predictions(dep_stop)
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
        return {"error": err}
    predictions_all_resp = fetch_predictions_all_stops()
    if predictions_all_resp.get("error"):
        predictions_all_resp = None
    red_shapes = parse_red_line_shape(shapes_resp)
    return {
        "error": None,
        "df_alerts": parse_alerts(alerts_resp),
        "df_departures": parse_departures(predictions_resp),
        "df_near_term": parse_near_term_arrivals(predictions_resp, vehicles_resp),
        "df_future": parse_future_arrivals(predictions_resp, vehicles_resp),
        "vehicles_map": parse_vehicles_for_map_enriched(vehicles_resp, predictions_all_resp),
        "red_shapes": red_shapes,
        "last_api_call_time": datetime.now(EASTERN),
    }


def _run_ai_report_sync(dep_stop: str, arr_stop: str, dep_name: str, arr_name: str) -> dict:
    """Fetch, format, query Ollama, write docx. Returns dict with report or error."""
    try:
        alerts_resp = fetch_alerts()
        pred_dep_resp = fetch_predictions_at_stop(dep_stop)
        pred_arr_resp = fetch_predictions_at_stop(arr_stop)
        vehicles_resp = fetch_vehicles()
        for name, resp in [
            ("alerts", alerts_resp),
            ("predictions dep", pred_dep_resp),
            ("predictions arr", pred_arr_resp),
            ("vehicles", vehicles_resp),
        ]:
            if resp.get("error"):
                return {"error": f"MBTA API error ({name}): {resp.get('message', 'Unknown')}"}
        df_a = build_alerts_df(alerts_resp)
        df_pd = build_predictions_df(pred_dep_resp)
        df_pa = build_predictions_df(pred_arr_resp)
        df_v = build_vehicles_df(vehicles_resp)
        formatted = format_data_for_ollama_compact(
            df_a, df_pd, df_pa, df_v, dep_label=dep_name, arr_label=arr_name
        )
        prompt = get_report_prompt(dep_name, arr_name)
        user_content = prompt.strip() + "\n\n---\nData:\n" + formatted
        report = query_ollama_cloud(user_content)
        reports_dir = Path(__file__).resolve().parent / "reports"
        out_path = write_report_docx(report, output_dir=reports_dir)
        return {"report": report, "saved_to": out_path.name}
    except Exception as e:
        return {"error": str(e)}


# 3. Server ##################################################################


def server(input, output, session):
    @reactive.extended_task
    async def refresh_task(dep_stop: str):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _do_refresh_sync, dep_stop)

    @reactive.extended_task
    async def ai_report_task(dep_stop: str, arr_stop: str, dep_name: str, arr_name: str):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            _run_ai_report_sync,
            dep_stop,
            arr_stop,
            dep_name,
            arr_name,
        )

    @reactive.effect
    @reactive.event(input.refresh, ignore_none=False)
    def _on_refresh_clicked():
        skip_next_timer_refresh.set(True)
        dep = input.dep_station() or "place-alfcl"
        ui.notification_show("Fetching data...", duration=2, type="message")
        refresh_task(dep)

    @reactive.effect
    def _apply_refresh_result():
        try:
            result = refresh_task.result()
        except SilentException:
            raise
        except Exception as e:
            api_error.set(str(e))
            return
        if not isinstance(result, dict):
            return
        if result.get("error"):
            api_error.set(result["error"])
            return
        api_error.set(None)
        df_alerts.set(result.get("df_alerts", pd.DataFrame()))
        df_departures.set(result.get("df_departures", pd.DataFrame()))
        df_near_term.set(result.get("df_near_term", pd.DataFrame()))
        df_future.set(result.get("df_future", pd.DataFrame()))
        vehicles_map.set(result.get("vehicles_map", []))
        red_shapes = result.get("red_shapes")
        if red_shapes:
            current = dict(shapes_by_route())
            current["Red"] = red_shapes
            shapes_by_route.set(current)
        last_api_call_time.set(result.get("last_api_call_time"))

    @reactive.effect
    @reactive.event(input.run_ai_report, ignore_none=False)
    def _on_ai_report_clicked():
        dep = input.dep_station() or "place-alfcl"
        arr = input.arr_station() or "place-cntsq"
        dep_name = get_station_name(dep)
        arr_name = get_station_name(arr)
        ai_report_error.set("")
        ai_report_text.set("Generating report...")
        ui.notification_show("Generating AI report...", duration=3, type="message")
        ai_report_task(dep, arr, dep_name, arr_name)

    @reactive.effect
    def _apply_ai_report_result():
        try:
            result = ai_report_task.result()
        except SilentException:
            raise
        except Exception as e:
            ai_report_error.set(str(e))
            ai_report_text.set("")
            return
        if not isinstance(result, dict):
            return
        if result.get("error"):
            ai_report_error.set(result["error"])
            ai_report_text.set("")
            return
        report = result.get("report", "")
        saved = result.get("saved_to", "")
        if saved:
            ai_report_text.set(report + f"\n\n---\n*Saved to: {saved}*")
        else:
            ai_report_text.set(report)

    @reactive.effect
    def _auto_refresh_timer():
        input.refresh()
        interval_min = input.refresh_interval_min()
        if interval_min is None or interval_min <= 0:
            return
        delay_sec = max(float(interval_min), MIN_AUTO_REFRESH_MINUTES) * 60
        if skip_next_timer_refresh():
            skip_next_timer_refresh.set(False)
            reactive.invalidate_later(delay_sec)
            return
        dep = input.dep_station() or "place-alfcl"
        refresh_task(dep)
        reactive.invalidate_later(delay_sec)

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
    def split_layout():
        """Split layout: left (tabs), right (report). Width from panel_ratio slider."""
        ratio = input.panel_ratio()
        if ratio is None:
            ratio = 55
        left_w = max(4, min(8, int(12 * ratio / 100)))
        right_w = 12 - left_w
        report_txt = ai_report_text()
        report_err = ai_report_error()
        if report_err:
            report_content = ui.div(
                ui.div(ui.strong("Error: "), report_err, class_="alert alert-danger", role="alert"),
            )
        elif report_txt:
            report_content = ui.div(
                ui.h4("AI Commuter Report", class_="mb-2"),
                ui.div(
                    ui.markdown(report_txt),
                    class_="p-3 bg-light rounded",
                    style="max-height: 500px; overflow-y: auto;",
                ),
            )
        else:
            report_content = ui.div(
                ui.h4("AI Commuter Report", class_="mb-2"),
                ui.p(
                    "Click 'Run AI Commuter Report' in the sidebar to generate a summary.",
                    class_="text-muted",
                ),
            )
        return ui.row(
            ui.column(left_w, make_tabs()),
            ui.column(
                right_w,
                ui.div(
                    report_content,
                    class_="border-start ps-3",
                ),
            ),
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
        height = input.map_height()
        if height is None or height < 400:
            height = 700
        height = min(900, max(400, int(height)))
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
            height=height,
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
