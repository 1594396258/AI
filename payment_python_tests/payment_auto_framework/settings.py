"""Backward-compatible settings alias. Use config.settings.AppSettings."""

from payment_python_tests.config.settings import AppSettings, load_settings

Settings = AppSettings

__all__ = ["AppSettings", "Settings", "load_settings"]
