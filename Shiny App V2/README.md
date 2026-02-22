# MBTA Red Line Tracker V2 (Shiny App)

Python Shiny app that extends V1 with an AI Commuter Report powered by Ollama Cloud. Displays Red Line service alerts, departures/arrivals for a selected station, a live map, and generates a .docx morning commute summary on demand.

## Table of Contents

- [Quick start: run the app](#quick-start-run-the-app)
- [Overview](#overview)
- [Requirements](#requirements)
- [Installation](#installation)
- [How to run](#how-to-run)
- [Configuration](#configuration)
- [Usage](#usage)
- [Deployment](#deployment)
- [Verification](#verification)
- [Tech stack](#tech-stack)

---

## Quick start: run the app

**Prerequisites:** Python 3.10+ installed. Get API keys: [MBTA](https://api-v3.mbta.com/portal) and [Ollama](https://ollama.com).

**Steps:**

1. Open a terminal in this folder (`Shiny App V2`).

2. Create a virtual environment and activate it:
   ```bash
   python -m venv .venv
   ```
   Then activate:
   - **Windows (cmd):** `.venv\Scripts\activate.bat`
   - **Windows (PowerShell):** `.venv\Scripts\Activate.ps1`
   - **macOS/Linux:** `source .venv/bin/activate`

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create your `.env` file:
   ```bash
   copy .env.example .env
   ```
   (Use `cp .env.example .env` on macOS/Linux.)

5. Edit `.env` and add your keys:
   ```
   MBTA_API_KEY=your_key_here
   OLLAMA_API_KEY=your_key_here
   ```

6. Run the app:
   ```bash
   shiny run app.py
   ```

7. Open **http://127.0.0.1:8000** in your browser. Click **Run API query** to load data; click **Run AI Commuter Report** to generate the summary.

---

## Overview

Shiny App V2 includes all V1 functionality plus:

- **Station dropdowns** — Select departure and arrival stations (default: Alewife → Central Square). The selected departure station applies to the next API refresh and all tables.
- **AI Commuter Report** — Click "Run AI Commuter Report" to synthesize MBTA data via Ollama Cloud into a half-page report. Report is displayed in a split panel and saved as a .docx file in `reports/` with naming `MBTA Red Line Commuter Report YYYY.MM.DD_HHMM.docx`.
- **Resizable layout** — Slider to adjust left/right panel widths. Map height control (400–900 px).
- **Token-optimized prompt** — Data sent to Ollama is compacted to reduce tokens while preserving report quality.

## Requirements

- Python 3.10+
- MBTA API key
- Ollama API key (for AI Commuter Report)

## Installation

1. Open a terminal in the `Shiny App V2` folder.
2. Create a virtual environment (recommended):

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # or: source .venv/bin/activate   # macOS/Linux
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and set your API keys (see [Configuration](#configuration)).

## How to run

From the **Shiny App V2** directory:

```bash
shiny run app.py
```

Optional: auto-reload and launch browser:

```bash
shiny run app.py --reload --launch-browser
```

The app is served at **http://127.0.0.1:8000** by default.

## Configuration

Copy `.env.example` to `.env` and set:

```bash
MBTA_API_KEY=your_mbta_key
OLLAMA_API_KEY=your_ollama_key
```

- **MBTA API key**: [MBTA Developer Portal](https://api-v3.mbta.com/portal)
- **Ollama API key**: [Ollama](https://ollama.com) for AI Commuter Report

## Usage

1. Run the app (see [How to run](#how-to-run)).
2. Select **Departure station** (default Alewife) and **Arrival station** (default Central Square).
3. Click **Run API query** to fetch data for the selected departure station.
4. Use the tabs for Service Alerts, Departures, Near-term Arrivals, Future Arrivals, and Live Map.
5. Click **Run AI Commuter Report** to generate a summary. The report appears in the right panel and is saved to `reports/`.
6. Use **Left panel width %** to resize the split layout; **Map height (px)** to resize the map.

## Deployment

The app can be containerized and deployed to DigitalOcean App Platform or similar.

### Docker (local)

From `Shiny App V2`:

```bash
docker build -t redline-v2 .
docker run -p 8080:8080 -e MBTA_API_KEY=xxx -e OLLAMA_API_KEY=yyy redline-v2
```

Then open `http://localhost:8080`.

### DigitalOcean App Platform

1. Create an app from the GitHub repo.
2. Set **Source Directory** to `Shiny App V2` (or configure build to use it).
3. Set **Dockerfile Path** to `Dockerfile`.
4. Add environment variables `MBTA_API_KEY` and `OLLAMA_API_KEY` as secrets.
5. Expose port 8080.

For containerized deployments, the `reports/` subfolder is ephemeral unless a volume is mounted. See [GitHub issue #5](https://github.com/JdogLloyd1/RedLineMBTATracker/issues/5) for future persistence options.

## Verification

- [ ] App starts: `shiny run app.py`
- [ ] UI: split layout, tabs, dropdowns, report panel, map height slider
- [ ] Run API query: data loads for selected station
- [ ] Run AI Commuter Report: report displays; .docx saved to `reports/`
- [ ] Error handling: missing keys or API failures show user-friendly messages
- [ ] Docker: `docker build` and `docker run` succeed with env vars

## Tech stack

- **Python**: 3.10+. Dependencies: `pip install -r requirements.txt`.
- **Shiny for Python**: [Shiny](https://shiny.posit.co/py/docs/install-create-run.html).
- **Ollama Cloud**: [Ollama API](https://ollama.com) for AI synthesis.
- **python-docx**: .docx report generation.
- **Plotly / shinywidgets**: Live map.

## Conventions

- Follow [`.cursor/rules/coding_style.mdc`](../.cursor/rules/coding_style.mdc).
- API logic in `api/`; AI reporter in `ai_reporter/`; layout helpers in `ui/`.

**For Cursor / AI-assisted editing:** See [README_CURSOR.md](README_CURSOR.md).
