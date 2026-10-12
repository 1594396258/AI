from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from payment_channel_mocks.app.channels.ppp import PppChannel
from payment_channel_mocks.app.core.config import MockSettings
from payment_channel_mocks.app.core.storage import ExchangeStore, utc_now


def build_ppp_router(store: ExchangeStore, settings: MockSettings) -> APIRouter:
    router = APIRouter(tags=["PPP channel"])
    ppp = PppChannel(store)

    async def read_body(request: Request) -> tuple[Any, int, str | None]:
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > settings.max_body_bytes:
                return "[body exceeds size limit]", 413, "Request body too large"
            raw.extend(chunk)
        try:
            def reject_constant(value: str) -> None:
                raise ValueError(f"Invalid JSON constant: {value}")

            parsed = json.loads(raw or b"{}", parse_constant=reject_constant)
        except (ValueError, UnicodeDecodeError):
            return raw.decode("utf-8", errors="replace"), 400, "Invalid JSON"
        if not isinstance(parsed, dict):
            return parsed, 400, "Request JSON must be an object"
        return parsed, 200, None

    def record_response(
        request: Request,
        request_id: str,
        scenario: dict[str, Any],
        body: Any,
        status_code: int,
        response_body: Any,
        order_no: str,
        channel_order_no: str,
        started_at: str,
        started_counter: float,
    ) -> JSONResponse:
        response = JSONResponse(
            response_body,
            status_code=status_code,
            headers={"X-Mock-Request-Id": request_id},
        )
        # Persist before returning: a subsequent admin read sees this exchange.
        store.record_exchange(
            request_id=request_id,
            run_id=scenario["run_id"],
            channel="ppp",
            direction="java_to_mock",
            method=request.method,
            request_url=str(request.url),
            path=request.url.path,
            query={key: request.query_params.getlist(key) for key in request.query_params},
            request_headers=dict(request.headers),
            request_body=body,
            response_status=status_code,
            response_headers=dict(response.headers),
            response_body=response_body,
            business_order_no=order_no,
            channel_order_no=channel_order_no,
            scenario_name=scenario["scenario_name"],
            started_at=started_at,
            finished_at=utc_now(),
            elapsed_ms=int((time.perf_counter() - started_counter) * 1000),
        )
        return response

    @router.post("/v1/payouts/")
    @router.post("/v1/payouts", include_in_schema=False)
    async def payout(request: Request) -> JSONResponse:
        started_at, started_counter = utc_now(), time.perf_counter()
        request_id = uuid.uuid4().hex
        scenario = await run_in_threadpool(store.get_scenario, "ppp")
        body, error_status, error = await read_body(request)
        if error:
            result = (
                error_status,
                {"code": "INVALID_REQUEST", "message": error},
                "",
                "",
            )
        else:
            order_no = str(body.get("merchantOrderId") or "")
            original_payout = None
            if order_no:
                original_payout = await run_in_threadpool(
                    store.find_payout_by_order, "ppp", order_no
                )
            if original_payout:
                scenario = await run_in_threadpool(
                    store.get_scenario, "ppp", original_payout["run_id"]
                )
            result = await run_in_threadpool(ppp.payout, body, scenario["config"])
        return await run_in_threadpool(
            record_response, request, request_id, scenario, body, *result,
            started_at, started_counter,
        )

    @router.get("/v1/payouts/status/{transaction_id}")
    def query(transaction_id: str, request: Request) -> JSONResponse:
        started_at, started_counter = utc_now(), time.perf_counter()
        request_id = uuid.uuid4().hex
        scenario = store.get_scenario("ppp")
        original_payout = store.find_by_channel_order_no("ppp", transaction_id)
        if original_payout:
            # Earlier orders keep their scenario even after a new run starts.
            scenario = store.get_scenario("ppp", original_payout["run_id"])
        result = ppp.query(transaction_id, scenario["config"])
        return record_response(
            request, request_id, scenario, {}, *result, started_at, started_counter
        )

    return router
