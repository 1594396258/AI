from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from payment_channel_mocks.app.api.admin_api import build_admin_router
from payment_channel_mocks.app.api.ppp_api import build_ppp_router
from payment_channel_mocks.app.core.config import MockSettings
from payment_channel_mocks.app.core.storage import ExchangeStore


def create_app(
    settings: MockSettings | None = None,
    *,
    database_path: str | Path | None = None,
) -> FastAPI:
    current_settings = settings or MockSettings.from_env()
    store = ExchangeStore(database_path or current_settings.database_path)
    app = FastAPI(title="Payment Channel Mocks", version="1.0.0")
    app.state.settings = current_settings
    app.state.store = store
    app.include_router(build_ppp_router(store, current_settings))
    app.include_router(build_admin_router(store, current_settings))
    return app
