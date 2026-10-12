from __future__ import annotations

import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient

from payment_channel_mocks.app.core.config import MockSettings
from payment_channel_mocks.app.main import create_app


def build_client(
    tmp_path, *, admin_token: str = "test-admin", max_body_bytes: int = 1024 * 1024
) -> TestClient:
    settings = MockSettings(
        host="127.0.0.1",
        port=18080,
        database_path=tmp_path / "mock.db",
        admin_token=admin_token,
        callback_timeout=1,
        ppp_callback_secret="test-secret",
        max_body_bytes=max_body_bytes,
    )
    return TestClient(create_app(settings, database_path=settings.database_path))


def admin_headers() -> dict[str, str]:
    return {"X-Mock-Admin-Token": "test-admin"}


def configure(client: TestClient, run_id: str = "run-1", **fields) -> None:
    response = client.post(
        "/__admin/scenarios",
        headers=admin_headers(),
        json={
            "run_id": run_id,
            "channel": "ppp",
            "scenario_name": "success-flow",
            "create_status": "pending",
            "query_status": "success",
            **fields,
        },
    )
    assert response.status_code == 200


def test_ppp_payout_and_query_are_persisted(tmp_path):
    with build_client(tmp_path) as client:
        configure(client)
        payout = client.post(
            "/v1/payouts/",
            headers={"Authorization": "Bearer test-pin"},
            json={"merchantOrderId": "order-1", "amount": "100.00"},
        )

        assert payout.status_code == 200
        assert payout.json() == {
            "status": "pending",
            "merchantOrderId": "order-1",
            "transactionId": "ppp-order-1",
            "amount": "100.00",
        }

        query = client.get("/v1/payouts/status/ppp-order-1")
        assert query.status_code == 200
        assert query.json()["status"] == "success"
        assert query.json()["merchantOrderId"] == "order-1"

        records = client.get(
            "/__admin/records",
            headers=admin_headers(),
            params={"run_id": "run-1", "business_order_no": "order-1"},
        ).json()["items"]

        assert len(records) == 2
        assert records[0]["method"] == "POST"
        assert records[0]["url"].endswith("/v1/payouts/")
        assert records[0]["headers"]["authorization"] == "Bearer test-pin"
        assert records[0]["body"]["amount"] == "100.00"
        assert records[0]["response_body"]["status"] == "pending"
        assert records[1]["method"] == "GET"
        assert records[1]["response_body"]["status"] == "success"


def test_repeated_payout_increments_attempt_number(tmp_path):
    with build_client(tmp_path) as client:
        configure(client, "run-retry")
        body = {"merchantOrderId": "order-retry", "amount": "1.00"}
        client.post("/v1/payouts/", json=body)
        client.post("/v1/payouts/", json=body)

        records = client.get(
            "/__admin/records",
            headers=admin_headers(),
            params={"run_id": "run-retry"},
        ).json()["items"]

        assert [item["attempt_no"] for item in records] == [1, 2]
        assert records[0]["request_hash"] == records[1]["request_hash"]


def test_admin_api_requires_token_when_configured(tmp_path):
    with build_client(tmp_path) as client:
        assert client.get("/__admin/health").status_code == 401
        assert client.get(
            "/__admin/health", headers=admin_headers()
        ).status_code == 200


@pytest.mark.parametrize("target_status", [200, 503])
def test_ppp_callback_is_signed_sent_and_recorded(tmp_path, monkeypatch, target_status):
    captured = {}

    def fake_post(self, url, json):
        captured.update(url=url, body=json, timeout=self.timeout)
        return SimpleNamespace(
            status_code=target_status,
            headers={"Content-Type": "text/plain"},
            text="SUCCESS",
            json=lambda: (_ for _ in ()).throw(ValueError()),
        )

    monkeypatch.setattr(
        "payment_channel_mocks.app.api.admin_api.HttpClient.post", fake_post
    )
    with build_client(tmp_path) as client:
        result = client.post(
            "/__admin/callbacks/ppp",
            headers=admin_headers(),
            json={
                "run_id": "run-callback",
                "target_url": "http://java.test/ppp/disburse/notify",
                "business_order_no": "order-2",
                "channel_order_no": "ppp-order-2",
                "amount": "10.00",
                "status": "success",
            },
        )

        assert result.status_code == 200
        assert result.json()["target_status"] == target_status
        # Known signing text independently specifies ordering, delimiter and values.
        expected_hash = hmac.new(
            b"test-secret", b"10.00|order-2|success|ppp-order-2|AUTO-MOCK-UTR",
            hashlib.sha256,
        ).hexdigest()
        assert captured["body"]["hash"] == expected_hash
        records = client.get(
            "/__admin/records",
            headers=admin_headers(),
            params={"run_id": "run-callback"},
        ).json()["items"]
        assert records[0]["direction"] == "mock_to_java"
        assert records[0]["response_status"] == target_status
        assert records[0]["response_body"] == "SUCCESS"


def test_restarting_service_preserves_scenario_and_records(tmp_path):
    with build_client(tmp_path) as client:
        configure(client, "run-restart", query_status="pending")
        client.post(
            "/v1/payouts/", json={"merchantOrderId": "restart-1", "amount": "2.00"}
        )

    with build_client(tmp_path) as restarted:
        query = restarted.get("/v1/payouts/status/ppp-restart-1")
        assert query.json()["status"] == "pending"
        assert query.json()["amount"] == "2.00"
        records = restarted.get(
            "/__admin/records", headers=admin_headers(), params={"run_id": "run-restart"}
        ).json()["items"]
        assert len(records) == 2
        assert records[1]["business_order_no"] == "restart-1"


def test_switching_run_does_not_change_old_order_query_or_retry(tmp_path):
    with build_client(tmp_path) as client:
        configure(client, "run-old", query_status="pending")
        old_body = {"merchantOrderId": "old-1", "amount": "10.00"}
        client.post("/v1/payouts/", json=old_body)
        configure(client, "run-new", create_status="failed", query_status="failed", amount="99.00")
        client.post("/v1/payouts/", json={"merchantOrderId": "new-1", "amount": "20.00"})

        old_query = client.get("/v1/payouts/status/ppp-old-1").json()
        assert old_query["status"] == "pending"
        assert old_query["amount"] == "10.00"
        retry = client.post("/v1/payouts/", json=old_body).json()
        assert retry["status"] == "pending"
        assert retry["amount"] == "10.00"
        new_query = client.get("/v1/payouts/status/ppp-new-1").json()
        assert new_query["status"] == "failed"
        assert new_query["amount"] == "99.00"

        old_records = client.get(
            "/__admin/records", headers=admin_headers(), params={"run_id": "run-old"}
        ).json()["items"]
        assert len(old_records) == 3
        assert all(item["business_order_no"] == "old-1" for item in old_records)
        assert old_records[-1]["attempt_no"] == 2


def test_same_run_can_change_query_from_pending_to_success(tmp_path):
    with build_client(tmp_path) as client:
        configure(client, "run-change", query_status="pending")
        client.post("/v1/payouts/", json={"merchantOrderId": "changing-1", "amount": "1.00"})
        assert client.get("/v1/payouts/status/ppp-changing-1").json()["status"] == "pending"
        configure(client, "run-change", query_status="success")
        assert client.get("/v1/payouts/status/ppp-changing-1").json()["status"] == "success"


def test_concurrent_retries_have_unique_continuous_attempt_numbers(tmp_path):
    with build_client(tmp_path) as client:
        configure(client, "run-concurrent")
        body = {"merchantOrderId": "same-order", "amount": "1.00"}
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: client.post("/v1/payouts/", json=body), range(12)))
        assert all(response.status_code == 200 for response in responses)
        records = client.get(
            "/__admin/records", headers=admin_headers(), params={"run_id": "run-concurrent"}
        ).json()["items"]
        assert sorted(item["attempt_no"] for item in records) == list(range(1, 13))
        assert len({item["request_id"] for item in records}) == 12
        assert len({item["request_hash"] for item in records}) == 1


@pytest.mark.parametrize("raw_body", ["not-json", '{"amount": NaN}', "[]", '{"orderNo": "wrong-field"}'])
def test_invalid_requests_are_rejected_and_recorded(tmp_path, raw_body):
    with build_client(tmp_path) as client:
        configure(client, "run-invalid")
        response = client.post("/v1/payouts/", content=raw_body)
        assert response.status_code == 400
        record = client.get(
            "/__admin/records/" + response.headers["X-Mock-Request-Id"], headers=admin_headers()
        ).json()
        assert record["run_id"] == "run-invalid"
        assert record["response_status"] == 400
        assert record["response_body"] == response.json()


def test_oversized_body_is_rejected_and_recorded(tmp_path):
    with build_client(tmp_path, max_body_bytes=64) as client:
        configure(client, "run-oversize")
        response = client.post("/v1/payouts/", content="x" * 65)
        assert response.status_code == 413
        record = client.get(
            "/__admin/records/" + response.headers["X-Mock-Request-Id"], headers=admin_headers()
        ).json()
        assert record["response_status"] == 413
        assert record["body"] == "[body exceeds size limit]"


def test_unknown_channel_order_does_not_return_fake_success(tmp_path):
    with build_client(tmp_path) as client:
        configure(client, "run-unknown")
        response = client.get("/v1/payouts/status/not-existing")
        assert response.status_code == 404
        assert response.json()["statusCode"] == "404"


def test_callback_timeout_is_recorded_for_failure_analysis(tmp_path, monkeypatch):
    def time_out(self, url, **kwargs):
        raise requests.Timeout("simulated target timeout")

    monkeypatch.setattr("payment_channel_mocks.app.api.admin_api.HttpClient.post", time_out)
    with build_client(tmp_path) as client:
        response = client.post(
            "/__admin/callbacks/ppp", headers=admin_headers(),
            json={
                "run_id": "run-timeout", "target_url": "http://java.test/ppp/disburse/notify?key=1&key=2",
                "business_order_no": "timeout-1", "channel_order_no": "ppp-timeout-1", "amount": "1.00",
            },
        )
        assert response.status_code == 502
        request_id = response.json()["detail"]["request_id"]
        record = client.get("/__admin/records/" + request_id, headers=admin_headers()).json()
        assert record["direction"] == "mock_to_java"
        assert record["response_status"] == 599
        assert "simulated target timeout" in record["response_body"]["error"]
        assert record["query"] == {"key": ["1", "2"]}
        assert record["url"] == "http://java.test/ppp/disburse/notify?key=1&key=2"


def test_record_cleanup_requires_explicit_run_and_keeps_other_runs(tmp_path):
    with build_client(tmp_path) as client:
        for run_id in ("run-keep", "run-remove"):
            configure(client, run_id)
            client.post("/v1/payouts/", json={"merchantOrderId": run_id, "amount": "1.00"})
        assert client.delete("/__admin/records", headers=admin_headers()).status_code == 422
        assert client.delete("/__admin/records", headers=admin_headers(), params={"run_id": ""}).status_code == 422
        response = client.delete("/__admin/records", headers=admin_headers(), params={"run_id": "run-remove"})
        assert response.json() == {"deleted": 1}
        records = client.get("/__admin/records", headers=admin_headers()).json()["items"]
        assert [item["run_id"] for item in records] == ["run-keep"]

