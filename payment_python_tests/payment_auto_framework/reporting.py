"""Backward-compatible report imports. Use payment_python_tests.reports."""

from payment_python_tests.reports.report_builder import (
    build_markdown_report,
    save_markdown_report,
)

__all__ = ["build_markdown_report", "save_markdown_report"]
