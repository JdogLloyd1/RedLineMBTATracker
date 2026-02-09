# Requirements for Shiny App of MBTA Red Line

## App Development Prompt:

Create a Shiny app in Python that

* Implements MBTA V3 API query upon user request
* Includes functional requirements per this file
* Has an attractive, modern, clean UI, with good spacing, colors, and typography
* Includes input controls for query parameters (if applicable)
* Displays results in a clear, formatted way
* Handles errors gracefully
* Follows best practices for Shiny app structure
* Has README documentation that is self-consistent and updates accordingly with changes

## Functionality:

* Button to run API query and update data
* UI to allow the user to set an API refresh rate in units of minutes
* Error handling for API errors, missing API keys, and invalid inputs
* **Service Alerts** – Red Line alerts: Severity, Description, Start Time, End Time, Status (Active/Inactive).
* **Departures** – From Alewife: Destination, Scheduled/Estimated Departure Time, Status (On Time/Delayed/Cancelled).
* **Near-term Arrivals** – To Alewife in next 10 min: Current stop, Scheduled/Estimated Arrival Time, Status.
* **Future Arrivals** – To Alewife in next 60 min: Current stop, Scheduled/Estimated Arrival Time, Status.
* **Live Map**: Plot the live locations of the trains and their direction of travel on a satellite map of the Boston metro area with MBTA subway routes displayed.
  * When hovering over train locations on the map, display a chip with its Train ID number, its direction of travel and final destination, the time it is expected at its next station, its next station, and how much time it is behind schedule.
  * Add an arrow to the train marker to show its direction of travel.

## Overall Process Flow:

1. Import necessary packages
2. Set up API calls
3. Parse data and build dataframes
4. Set up Shiny dashboard UI
5. Display data on dashboard

## Deliverable Files:

* Main app file `app.py`
* UI components
* Server logic
* Any helper functions or utilities
* Any other necessary files to execute the app functionality
* Clean file tree organization with intuitive folder names
* README.md documentation for developers according to the rule "developer_readme_format.mdc" including:
  * Overview of what the app does
  * Installation instructions
  * How to run the app
  * API requirements (API key setup, etc.)
  * Screenshots of the app in action
  * Usage instructions
* README.md documentation for Cursor to continue further development at a later date. Ensure documentation is self-consistent and consistent with the developer README

## Tools to Use:

* This requirements document
* For instructions on implementing Service alerts, departures, and arrivals, see .cursor\plans\alewife_red_line_api_implementation.md
* 000_RedLineTrackerProject\API Call Demo.py
* MBTA V3 API documentation
* Shiny package documentation
* Streamlit package documentation

## Verification Requirements:

* The app starts without errors
* The UI displays correctly
* The API query executes successfully
* Results are displayed properly
* Error handling works as expected
