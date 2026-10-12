"""Local HTTP walkthrough of the mock service, without Java or test credentials."""

from __future__ import annotations

import argparse
import uuid

import requests

from payment_channel_mocks.app.core.config import MockSettings
from payment_channel_mocks.app.core.http_client import HttpClient


def main() -> None:
    settings = MockSettings.from_env()
    parser = argparse.ArgumentParser(description="演示独立 PPP Mock 的场景和请求记录")
    parser.add_argument(
        "--base-url", default=f"http://127.0.0.1:{settings.port}",
        help="已启动的独立 Mock 地址，默认使用本机 MOCK_PORT",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    http = HttpClient(timeout=10)
    admin_headers = {"X-Mock-Admin-Token": settings.admin_token}
    run_id = f"DEMO-{uuid.uuid4().hex}"
    order_no = f"order-{uuid.uuid4().hex}"

    def call(method: str, path: str, **kwargs):
        response = http.request(method, base_url + path, **kwargs)
        response.raise_for_status()
        return response.json()

    try:
        call("GET", "/__admin/health", headers=admin_headers)
        call(
            "POST", "/__admin/scenarios", headers=admin_headers,
            json={
                "run_id": run_id, "channel": "ppp", "scenario_name": "local-demo",
                "create_status": "pending", "query_status": "success",
            },
        )
        payout = call(
            "POST", "/v1/payouts/",
            headers={"Authorization": "Bearer demo-pin"},
            json={"merchantOrderId": order_no, "amount": "100.00"},
        )
        assert payout["status"] == "pending", payout
        query = call("GET", "/v1/payouts/status/" + payout["transactionId"])
        assert query["status"] == "success", query
        records = call(
            "GET", "/__admin/records", headers=admin_headers,
            params={"run_id": run_id, "business_order_no": order_no},
        )["items"]
        assert len(records) == 2, records
        assert records[0]["body"]["amount"] == "100.00"
        assert records[0]["headers"]["authorization"] == "Bearer demo-pin"
        assert records[0]["response_body"]["status"] == "pending"
        assert records[1]["response_body"]["status"] == "success"
    except requests.RequestException as exc:
        parser.exit(1, f"无法完成演示：{exc}\n请先启动 Mock，并核对地址和管理 Token。\n")

    print("演示通过：配置场景 -> PPP 下单 pending -> PPP 查询 success -> 读取并断言 2 条数据库记录。")
    print("这是 Mock 自身的演示；真实回归仍由原测试框架调用 Java。")
    print(f"run_id: {run_id}")
    print(f"订单号: {order_no}")
    print(f"记录地址: {base_url}/__admin/records?run_id={run_id}")
    print(f"本机默认数据库: {settings.database_path}")
    print("记录已保留，可以在 Swagger 中带管理 Token 查询。")


if __name__ == "__main__":
    main()
