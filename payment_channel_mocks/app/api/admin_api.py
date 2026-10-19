from __future__ import annotations

import secrets
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlsplit

import requests
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import AnyHttpUrl, BaseModel, Field

from payment_channel_mocks.app.core.config import MockSettings
from payment_channel_mocks.app.core.http_client import HttpClient
from payment_channel_mocks.app.core.signing import hmac_sha256_sorted_values
from payment_channel_mocks.app.core.storage import ExchangeStore, utc_now


class ScenarioRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=128)
    channel: str = "ppp"
    scenario_name: str = "default"
    create_status: str = "pending"
    query_status: str = "success"
    amount: str | None = None
    transaction_id: str | None = None
    response_status_code: int = Field(default=200, ge=200, le=599)
    delay_ms: int = Field(default=0, ge=0, le=60_000)


class PppCallbackRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=128)
    target_url: AnyHttpUrl
    business_order_no: str = Field(min_length=1)
    channel_order_no: str = Field(min_length=1)
    amount: str = Field(min_length=1)
    status: str = "success"
    utr: str = "AUTO-MOCK-UTR"


def build_admin_router(store: ExchangeStore, settings: MockSettings) -> APIRouter:
    def require_admin(
        x_mock_admin_token: str = Header(default="", alias="X-Mock-Admin-Token"),
    ) -> None:
        if settings.admin_token and not secrets.compare_digest(
            x_mock_admin_token.encode(), settings.admin_token.encode()
        ):
            raise HTTPException(status_code=401, detail="Invalid mock admin token")

    router = APIRouter(
        prefix="/__admin", tags=["Mock management"],
        dependencies=[Depends(require_admin)],
    )

    @router.get("/health")
    def health() -> dict[str, Any]:
        store.get_scenario("ppp")
        return {"status": "UP", "channels": ["ppp"]}

    @router.post("/scenarios")
    def configure(payload: ScenarioRequest) -> dict[str, Any]:
        data = payload.model_dump()  #转字典
        if data["channel"] != "ppp":
            raise HTTPException(status_code=400, detail="Only ppp is implemented")
        config = {
            key: value for key, value in data.items()
            if key not in {"channel", "run_id", "scenario_name"}
        }
        return store.set_scenario(
            channel=data["channel"], run_id=data["run_id"],
            scenario_name=data["scenario_name"], config=config,
        )

    @router.get("/scenarios/{channel}")
    def current_scenario(channel: str, run_id: str = "") -> dict[str, Any]:
        return store.get_scenario(channel, run_id)

    @router.get("/records")
    def records(
        run_id: str = "", channel: str = "", business_order_no: str = "",
        direction: str = "", limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, Any]:
        items = store.list_records(
            run_id=run_id, channel=channel, business_order_no=business_order_no,
            direction=direction, limit=limit,
        )
        return {"count": len(items), "items": items}

    @router.get("/records/{request_id}")
    def record_detail(request_id: str) -> dict[str, Any]:
        item = store.get_record(request_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Record not found")
        return item

    @router.delete("/records")
    def delete_records(run_id: str = Query(min_length=1)) -> dict[str, int]:
        return {"deleted": store.delete_records(run_id)}

    @router.post("/callbacks/ppp")
    def send_ppp_callback(payload: PppCallbackRequest) -> dict[str, Any]:
        if not settings.ppp_callback_secret:
            raise HTTPException(status_code=400, detail="PPP_CALLBACK_SECRET missing")
        target_url = str(payload.target_url)
        callback_body = {
            "status": payload.status,
            "merchantOrderId": payload.business_order_no,
            "transactionId": payload.channel_order_no,
            "amount": payload.amount,
            "utr": payload.utr,
        }
        callback_body["hash"] = hmac_sha256_sorted_values(
            callback_body, settings.ppp_callback_secret
        )
        request_id = uuid.uuid4().hex
        started_at, started_counter = utc_now(), time.perf_counter()
        response_status, response_headers = 599, {}
        request_headers = {"Content-Type": "application/json"}
        callback_error: str | None = None
        try:
            response = HttpClient(settings.callback_timeout).post(
                target_url, json=callback_body
            )
            response_status = response.status_code
            response_headers = dict(response.headers)
            prepared = getattr(response, "request", None)
            if prepared is not None:
                request_headers = dict(prepared.headers)
            try:
                response_body: Any = response.json()
            except ValueError:
                response_body = response.text
        except requests.RequestException as exc:
            if exc.request is not None:
                request_headers = dict(exc.request.headers)
            callback_error = f"{type(exc).__name__}: {exc}"
            response_body = {"error": callback_error, "target_url": target_url}
        store.record_exchange(
            request_id=request_id, run_id=payload.run_id, channel="ppp",
            direction="mock_to_java", method="POST", path=urlsplit(target_url).path,
            request_url=target_url,
            query=parse_qs(urlsplit(target_url).query, keep_blank_values=True),
            request_headers=request_headers,
            request_body=callback_body, response_status=response_status,
            response_headers=response_headers, response_body=response_body,
            business_order_no=payload.business_order_no,
            channel_order_no=payload.channel_order_no, scenario_name="callback",
            started_at=started_at, finished_at=utc_now(),
            elapsed_ms=int((time.perf_counter() - started_counter) * 1000),
        )
        if callback_error:
            raise HTTPException(
                status_code=502,
                detail={"request_id": request_id, "error": callback_error},
            )
        return {
            "request_id": request_id, "target_status": response_status,
            "target_body": response_body,
        }

    return router
