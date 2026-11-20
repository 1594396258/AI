from __future__ import annotations

import json
import secrets
import time
import uuid
from typing import Any
from loguru import logger
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from payment_channel_mocks.app.channels.ppp import PppChannel
from payment_channel_mocks.app.core.config import MockSettings
from payment_channel_mocks.app.core.signing import verify_hmac_sha256_sorted_values
from payment_channel_mocks.app.core.storage import ExchangeStore, utc_now


def build_ppp_router(store: ExchangeStore, settings: MockSettings) -> APIRouter:
    router = APIRouter(tags=["PPP channel"])
    ppp = PppChannel(store)

    def authentication_error(
        request: Request, body: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, str]] | None:
        # GET uses Bearer only; POST additionally requires the payout signing key.
        if not settings.ppp_pin:
            return 503, {
                "code": "MOCK_AUTH_NOT_CONFIGURED",
                "message": "PPP_PIN is required",
            }
        if body is not None and not settings.ppp_request_secret:
            return 503, {
                "code": "MOCK_AUTH_NOT_CONFIGURED",
                "message": "PPP_REQUEST_SECRET is required",
            }
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(
            token.encode("utf-8"), settings.ppp_pin.encode("utf-8")
        ):
            return 401, {
                "code": "INVALID_AUTHORIZATION",
                "message": "Missing or invalid PPP Bearer token",
            }
        if body is not None and not verify_hmac_sha256_sorted_values(
            body, settings.ppp_request_secret
        ):
            return 401, {
                "code": "INVALID_SIGNATURE",
                "message": "Missing or invalid PPP hash",
            }
        return None

    async def read_body(request: Request) -> tuple[Any, int, str | None]:
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > settings.max_body_bytes:
                return "[body exceeds size limit]", 413, "Request body too large"
            raw.extend(chunk)
        try:
            def reject_constant(value: str) -> None:
                raise ValueError(f"Invalid JSON constant: {value}")

            parsed = json.loads(raw or b"{}", parse_constant=reject_constant) # 转成字典
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

    @router.post("/ppp/v1/payouts/")
    @router.post("/ppp/v1/payouts", include_in_schema=False)
    async def payout(request: Request) -> JSONResponse:
        started_at, started_counter = utc_now(), time.perf_counter()
        request_id = uuid.uuid4().hex
        scenario = await run_in_threadpool(store.get_scenario, "ppp") # 获取场景配置
        body, error_status, error = await read_body(request)  # 读取请求参数并校验
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
            failure = authentication_error(request, body)  #鉴权
            if failure:
                result = (*failure, order_no, "")
            else:
                result = await run_in_threadpool(ppp.payout, body, scenario["config"]) #代付
        return await run_in_threadpool(
            record_response, request, request_id, scenario, body, *result,
            started_at, started_counter
        ) # 写入数据库 sqlite3

    @router.get("/ppp/v1/payouts/status/{transaction_id}")
    def query(transaction_id: str, request: Request) -> JSONResponse:
        started_at, started_counter = utc_now(), time.perf_counter()
        request_id = uuid.uuid4().hex
        scenario = store.get_scenario("ppp")
        original_payout = store.find_by_channel_order_no("ppp", transaction_id)
        if original_payout:
            # Earlier orders keep their scenario even after a new run starts.
            scenario = store.get_scenario("ppp", original_payout["run_id"])
        failure = authentication_error(request)
        if failure:
            order_no = original_payout["business_order_no"] if original_payout else ""
            result = (*failure, order_no, transaction_id)
        else:
            result = ppp.query(transaction_id, scenario["config"])
        return record_response(
            request, request_id, scenario, {}, *result, started_at, started_counter
        )

    return router
