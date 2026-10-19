from __future__ import annotations

import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient

from payment_channel_mocks.app.core.config import MockSettings
from payment_channel_mocks.app.core.signing import hmac_sha256_sorted_values
from payment_channel_mocks.app.main import create_app


REQUEST_SECRET = "test-request-secret"
PPP_PIN = "test-pin"


def build_client(
    tmp_path,
    *,
    admin_token: str = "test-admin",
    max_body_bytes: int = 1024 * 1024,
    ppp_request_secret: str = REQUEST_SECRET,
    ppp_pin: str = PPP_PIN,
) -> TestClient:
    settings = MockSettings(
        host="127.0.0.1",
        port=18080,
        database_path=tmp_path / "mock.db",
        admin_token=admin_token,
        callback_timeout=1,
        ppp_callback_secret="test-secret",
        max_body_bytes=max_body_bytes,
        ppp_request_secret=ppp_request_secret,
        ppp_pin=ppp_pin,
    )
    return TestClient(
        create_app(settings, database_path=settings.database_path),
        headers={"Authorization": f"Bearer {ppp_pin}"},
    )


def signed_payload(body: dict, secret: str = REQUEST_SECRET) -> dict:
    payload = dict(body)
    payload["hash"] = hmac_sha256_sorted_values(payload, secret)
    return payload


def exchange_record(client: TestClient, response) -> dict:
    record = client.get(
        "/__admin/records/" + response.headers["X-Mock-Request-Id"],
        headers=admin_headers(),
    )
    assert record.status_code == 200
    return record.json()


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
        body = signed_payload({"merchantOrderId": "order-1", "amount": "100.00"})
        payout = client.post(
            "/ppp/v1/payouts/",
            headers={"Authorization": "Bearer test-pin"},
            json=body,
        )

        assert payout.status_code == 200
        assert payout.json() == {
            "status": "pending",
            "merchantOrderId": "order-1",
            "transactionId": "ppp-order-1",
            "amount": "100.00",
        }

        query = client.get("/ppp/v1/payouts/status/ppp-order-1")
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
        assert records[0]["url"].endswith("/ppp/v1/payouts/")
        assert records[0]["headers"]["authorization"] == "Bearer test-pin"
        assert records[0]["body"] == body
        assert records[0]["response_body"]["status"] == "pending"
        assert records[1]["method"] == "GET"
        assert records[1]["response_body"]["status"] == "success"


def test_repeated_payout_increments_attempt_number(tmp_path):
    with build_client(tmp_path) as client:
        configure(client, "run-retry")
        body = signed_payload({"merchantOrderId": "order-retry", "amount": "1.00"})
        assert client.post("/ppp/v1/payouts/", json=body).status_code == 200
        assert client.post("/ppp/v1/payouts/", json=body).status_code == 200

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
            "/ppp/v1/payouts/",
            json=signed_payload({"merchantOrderId": "restart-1", "amount": "2.00"}),
        )

    with build_client(tmp_path) as restarted:
        query = restarted.get("/ppp/v1/payouts/status/ppp-restart-1")
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
        old_body = signed_payload({"merchantOrderId": "old-1", "amount": "10.00"})
        client.post("/ppp/v1/payouts/", json=old_body)
        configure(client, "run-new", create_status="failed", query_status="failed", amount="99.00")
        client.post(
            "/ppp/v1/payouts/",
            json=signed_payload({"merchantOrderId": "new-1", "amount": "20.00"}),
        )

        old_query = client.get("/ppp/v1/payouts/status/ppp-old-1").json()
        assert old_query["status"] == "pending"
        assert old_query["amount"] == "10.00"
        retry = client.post("/ppp/v1/payouts/", json=old_body).json()
        assert retry["status"] == "pending"
        assert retry["amount"] == "10.00"
        new_query = client.get("/ppp/v1/payouts/status/ppp-new-1").json()
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
        client.post(
            "/ppp/v1/payouts/",
            json=signed_payload({"merchantOrderId": "changing-1", "amount": "1.00"}),
        )
        assert client.get("/ppp/v1/payouts/status/ppp-changing-1").json()["status"] == "pending"
        configure(client, "run-change", query_status="success")
        assert client.get("/ppp/v1/payouts/status/ppp-changing-1").json()["status"] == "success"


def test_concurrent_retries_have_unique_continuous_attempt_numbers(tmp_path):
    with build_client(tmp_path) as client:
        configure(client, "run-concurrent")
        body = signed_payload({"merchantOrderId": "same-order", "amount": "1.00"})
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: client.post("/ppp/v1/payouts/", json=body), range(12)))
        assert all(response.status_code == 200 for response in responses)
        records = client.get(
            "/__admin/records", headers=admin_headers(), params={"run_id": "run-concurrent"}
        ).json()["items"]
        assert sorted(item["attempt_no"] for item in records) == list(range(1, 13))
        assert len({item["request_id"] for item in records}) == 12
        assert len({item["request_hash"] for item in records}) == 1


@pytest.mark.parametrize("raw_body", ["not-json", '{"amount": NaN}', "[]"])
def test_invalid_requests_are_rejected_and_recorded(tmp_path, raw_body):
    with build_client(tmp_path) as client:
        configure(client, "run-invalid")
        response = client.post("/ppp/v1/payouts/", content=raw_body)
        assert response.status_code == 400
        record = client.get(
            "/__admin/records/" + response.headers["X-Mock-Request-Id"], headers=admin_headers()
        ).json()
        assert record["run_id"] == "run-invalid"
        assert record["response_status"] == 400
        assert record["response_body"] == response.json()


def test_signed_request_without_merchant_order_id_is_rejected_and_recorded(tmp_path):
    with build_client(tmp_path) as client:
        response = client.post(
            "/ppp/v1/payouts/", json=signed_payload({"orderNo": "wrong-field"})
        )
        assert response.status_code == 400
        assert response.json()["error"] == "merchantOrderId is required"
        assert exchange_record(client, response)["response_status"] == 400


def test_oversized_body_is_rejected_and_recorded(tmp_path):
    with build_client(tmp_path, max_body_bytes=64) as client:
        configure(client, "run-oversize")
        response = client.post("/ppp/v1/payouts/", content="x" * 65)
        assert response.status_code == 413
        record = client.get(
            "/__admin/records/" + response.headers["X-Mock-Request-Id"], headers=admin_headers()
        ).json()
        assert record["response_status"] == 413
        assert record["body"] == "[body exceeds size limit]"


def test_unknown_channel_order_does_not_return_fake_success(tmp_path):
    with build_client(tmp_path) as client:
        configure(client, "run-unknown")
        response = client.get("/ppp/v1/payouts/status/not-existing")
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
            client.post(
                "/ppp/v1/payouts/",
                json=signed_payload({"merchantOrderId": run_id, "amount": "1.00"}),
            )
        assert client.delete("/__admin/records", headers=admin_headers()).status_code == 422
        assert client.delete("/__admin/records", headers=admin_headers(), params={"run_id": ""}).status_code == 422
        response = client.delete("/__admin/records", headers=admin_headers(), params={"run_id": "run-remove"})
        assert response.json() == {"deleted": 1}
        records = client.get("/__admin/records", headers=admin_headers()).json()["items"]
        assert [item["run_id"] for item in records] == ["run-keep"]


@pytest.mark.parametrize(
    "invalid_hash",
    [
        None, 0, False, [], {}, "", "0" * 63, "0" * 65,
        "g" * 64, "A" * 64, "签" * 64, " " * 64, "0" * 64,
    ],
)
def test_invalid_signatures_are_rejected_and_recorded(tmp_path, invalid_hash):
    with build_client(tmp_path) as client:
        configure(client, "run-bad-signature")
        body = {"merchantOrderId": "bad-signature", "amount": "100.00", "hash": invalid_hash}
        response = client.post("/ppp/v1/payouts/", json=body)

        assert response.status_code == 401
        assert response.json()["code"] == "INVALID_SIGNATURE"
        record = exchange_record(client, response)
        assert record["run_id"] == "run-bad-signature"
        assert record["body"] == body
        assert record["response_status"] == 401
        assert record["response_body"] == response.json()
        assert record["business_order_no"] == "bad-signature"
        assert record["channel_order_no"] == ""
        assert client.get("/ppp/v1/payouts/status/ppp-bad-signature").status_code == 404


@pytest.mark.parametrize(
    "change",
    ["missing_hash", "amount", "merchantOrderId", "added_field", "removed_field", "wrong_key", "callback_key"],
)
def test_tampered_or_incorrectly_signed_payout_is_rejected(tmp_path, change):
    body = signed_payload({"merchantOrderId": "tampered-1", "amount": "100.00"})
    if change == "missing_hash":
        body.pop("hash")
    elif change == "amount":
        body["amount"] = "1000.00"
    elif change == "merchantOrderId":
        body["merchantOrderId"] = "tampered-2"
    elif change == "added_field":
        body["customerName"] = "added after signing"
    elif change == "removed_field":
        body.pop("amount")
    else:
        key = "test-secret" if change == "callback_key" else "wrong-secret"
        body = signed_payload(body, secret=key)

    with build_client(tmp_path) as client:
        response = client.post("/ppp/v1/payouts/", json=body)
        assert response.status_code == 401
        assert response.json()["code"] == "INVALID_SIGNATURE"
        record = exchange_record(client, response)
        assert record["body"] == body
        assert record["channel_order_no"] == ""


@pytest.mark.parametrize("method", ["POST", "GET"])
@pytest.mark.parametrize(
    "authorization",
    [None, "", "test-pin", "Basic test-pin", "Bearer wrong-pin", "Bearer", "Bearer ", "Bearer test-pin ", "Bearer  test-pin"],
)
def test_missing_or_invalid_bearer_is_rejected_and_recorded(tmp_path, method, authorization):
    body = signed_payload({"merchantOrderId": "auth-1", "amount": "1.00"})
    with build_client(tmp_path) as client:
        configure(client, "run-auth")
        if method == "GET":
            assert client.post("/ppp/v1/payouts/", json=body).status_code == 200
            request = client.build_request("GET", "/ppp/v1/payouts/status/ppp-auth-1")
        else:
            request = client.build_request("POST", "/ppp/v1/payouts/", json=body)
        # Explicitly remove the client's default header to exercise missing auth.
        request.headers.pop("Authorization", None)
        if authorization is not None:
            request.headers["Authorization"] = authorization
        response = client.send(request)

        assert response.status_code == 401
        assert response.json()["code"] == "INVALID_AUTHORIZATION"
        record = exchange_record(client, response)
        assert record["run_id"] == "run-auth"
        assert record["method"] == method
        assert record["response_status"] == 401
        assert record["response_body"] == response.json()
        if method == "POST":
            assert record["channel_order_no"] == ""
            assert client.get("/ppp/v1/payouts/status/ppp-auth-1").status_code == 404
        else:
            assert client.get("/ppp/v1/payouts/status/ppp-auth-1").status_code == 200


@pytest.mark.parametrize("authorization", ["Bearer test-pin", "bearer test-pin", "BEARER test-pin"])
def test_bearer_scheme_is_case_insensitive(tmp_path, authorization):
    with build_client(tmp_path) as client:
        headers = {"Authorization": authorization}
        payout = client.post(
            "/ppp/v1/payouts/", headers=headers,
            json=signed_payload({"merchantOrderId": "scheme-1", "amount": "1.00"}),
        )
        assert payout.status_code == 200
        assert client.get("/ppp/v1/payouts/status/ppp-scheme-1", headers=headers).status_code == 200


def test_payout_without_trailing_slash_also_requires_signature(tmp_path):
    with build_client(tmp_path) as client:
        body = {"merchantOrderId": "no-slash-1", "amount": "1.00"}
        assert client.post("/ppp/v1/payouts", json=body).status_code == 401
        assert client.post("/ppp/v1/payouts", json=signed_payload(body)).status_code == 200


@pytest.mark.parametrize(
    "settings_kwargs, method, missing_setting",
    [
        ({"ppp_pin": ""}, "POST", "PPP_PIN"),
        ({"ppp_pin": ""}, "GET", "PPP_PIN"),
        ({"ppp_request_secret": ""}, "POST", "PPP_REQUEST_SECRET"),
    ],
)
def test_missing_auth_configuration_fails_closed(tmp_path, settings_kwargs, method, missing_setting):
    with build_client(tmp_path, **settings_kwargs) as client:
        if method == "POST":
            response = client.post(
                "/ppp/v1/payouts/",
                json=signed_payload({"merchantOrderId": "unconfigured-1", "amount": "1.00"}),
            )
        else:
            response = client.get("/ppp/v1/payouts/status/ppp-unconfigured-1")
        assert response.status_code == 503
        assert response.json()["code"] == "MOCK_AUTH_NOT_CONFIGURED"
        assert missing_setting in response.json()["message"]
        assert exchange_record(client, response)["response_status"] == 503


def test_query_requires_only_bearer_not_request_secret_or_hash(tmp_path):
    with build_client(tmp_path) as client:
        assert client.post(
            "/ppp/v1/payouts/",
            json=signed_payload({"merchantOrderId": "query-auth-1", "amount": "2.00"}),
        ).status_code == 200

    with build_client(tmp_path, ppp_request_secret="") as client:
        response = client.get("/ppp/v1/payouts/status/ppp-query-auth-1")
        assert response.status_code == 200
        assert response.json()["merchantOrderId"] == "query-auth-1"
        assert response.json()["amount"] == "2.00"


@pytest.mark.parametrize("failure_type", ["signature", "authorization"])
def test_rejected_first_payout_does_not_bind_order_to_old_run(tmp_path, failure_type):
    body = {"merchantOrderId": "unbound-1", "amount": "10.00"}
    with build_client(tmp_path) as client:
        configure(client, "run-rejected", create_status="failed", query_status="pending")
        if failure_type == "signature":
            rejected = client.post("/ppp/v1/payouts/", json=body)
        else:
            rejected = client.post(
                "/ppp/v1/payouts/", json=signed_payload(body),
                headers={"Authorization": "Bearer wrong-pin"},
            )
        assert rejected.status_code == 401
        assert exchange_record(client, rejected)["channel_order_no"] == ""

        configure(client, "run-accepted", create_status="initiated", query_status="success")
        accepted = client.post("/ppp/v1/payouts/", json=signed_payload(body))
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "initiated"
        assert exchange_record(client, accepted)["run_id"] == "run-accepted"
        query = client.get("/ppp/v1/payouts/status/ppp-unbound-1")
        assert query.json()["status"] == "success"
        assert exchange_record(client, query)["run_id"] == "run-accepted"


@pytest.mark.parametrize("failure_type", ["signature", "authorization"])
def test_rejected_retry_does_not_hide_accepted_payout(tmp_path, failure_type):
    body = {"merchantOrderId": "accepted-1", "amount": "10.00"}
    with build_client(tmp_path) as client:
        configure(client, "run-original", query_status="pending")
        assert client.post("/ppp/v1/payouts/", json=signed_payload(body)).status_code == 200
        if failure_type == "signature":
            rejected = client.post("/ppp/v1/payouts/", json={**body, "amount": "99.00"})
        else:
            rejected = client.post(
                "/ppp/v1/payouts/", json=signed_payload({**body, "amount": "99.00"}),
                headers={"Authorization": "Bearer wrong-pin"},
            )
        assert rejected.status_code == 401
        configure(client, "run-other", create_status="failed", query_status="failed", amount="99.00")

        query = client.get("/ppp/v1/payouts/status/ppp-accepted-1")
        assert query.status_code == 200
        assert query.json()["status"] == "pending"
        assert query.json()["amount"] == "10.00"
        assert exchange_record(client, query)["run_id"] == "run-original"
        retry = client.post("/ppp/v1/payouts/", json=signed_payload(body))
        assert retry.status_code == 200
        assert retry.json()["status"] == "pending"
        assert exchange_record(client, retry)["run_id"] == "run-original"

