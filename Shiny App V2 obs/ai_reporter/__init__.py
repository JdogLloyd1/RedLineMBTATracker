# ai_reporter/__init__.py
# Ollama Cloud AI Commuter Report for MBTA Red Line.

from ai_reporter.reporter import (
    build_alerts_df,
    build_predictions_df,
    build_vehicles_df,
    format_data_for_ollama_compact,
    get_report_prompt,
    query_ollama_cloud,
    write_report_docx,
)

__all__ = [
    "build_alerts_df",
    "build_predictions_df",
    "build_vehicles_df",
    "format_data_for_ollama_compact",
    "get_report_prompt",
    "query_ollama_cloud",
    "write_report_docx",
]
