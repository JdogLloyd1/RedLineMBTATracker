# Requirements for Shiny App V2 of MBTA Red Line

## App Development Prompt:

Create a Shiny app in Python based on the first Shiny App we built together but with added Ollama Cloud AI data reporter functionality.

This Shiny App V2 should:

* Contain all original functionality of Shiny App V1
* Request morning commute report summarization from Ollama Cloud upon user request. Use "AI Data Reporter Module" folder as a baseline, but consider ways to decrease the amount of tokens/data sent to Ollama without compromising report quality and content
* Has an attractive, modern, clean UI, with good spacing, colors, and typography
* Includes input controls for query parameters (if applicable)
* Displays results in a clear, formatted way
* Handles errors gracefully
* Follows best practices for Shiny app structure
* Has README documentation that is self-consistent and updates accordingly with changes
* Include Docker file and necessary hooks to deploy app to Digital Ocean or similar hosting platform

## Functionality:

* All functionality of the Shiny App V1
* Button to run the Ollama AI Commuter Report
* Dropdown menus to select the departure station and arrival station to use when generating the AI Commuter Report
* Display the Commuter Report on a split screen in the app window, with the commuter report on the right side and the App V1 tables and live map slid over on the left side
* Generates a .docx of the Commuter Report in a subfolder for vaulting, with naming convention "MBTA Red Line Commuter Report Year.Month.Day"

## Deliverable Files:

* Main app file `app.py`
* UI components
* Server logic
* Any helper functions or utilities
* Any other necessary files to execute the app functionality
* Clean file tree organization with intuitive folder names
* Updated README.md documentation for developers according to the rule "developer_readme_format.mdc" including
* Updated README.md documentation for Cursor to continue further development at a later date. Ensure documentation is self-consistent and consistent with the developer README

## Verification Requirements:

* The app starts without errors
* The UI displays correctly
* The API query executes successfully
* Ollama Cloud query executes successfully
* MBTA API results and AI Commuter Report are displayed properly in app
* Word .docx reports generated as expected
* Error handling works as expected
