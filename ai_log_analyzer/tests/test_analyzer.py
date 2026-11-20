from analyzer import analyze_log, sanitize_log


def test_timeout_is_detected():
    log = """2026-11-20 12:00:00 ERROR request failed
java.net.SocketTimeoutException: Read timed out
    at com.demo.OrderService.confirm(OrderService.java:42)
"""
    report = analyze_log(log)
    assert report["severity"] == "high"
    assert report["confidence"] >= 80
    assert "超时" in report["likely_causes"][0]["title"]
    assert "OrderService.java:42" in report["project_frame"]


def test_secrets_are_redacted():
    text = "password=hello123 api_key=sk-test_1234567890123456 user=a@example.com host=192.168.1.8"
    sanitized, count = sanitize_log(text)
    assert "hello123" not in sanitized
    assert "sk-test" not in sanitized
    assert "a@example.com" not in sanitized
    assert "192.168.1.8" not in sanitized
    assert count == 4


def test_unknown_error_gets_safe_fallback():
    report = analyze_log("custom application message without a known signature")
    assert report["confidence"] == 35
    assert report["actions"]


def test_empty_log_is_rejected():
    try:
        analyze_log("   ")
    except ValueError as exc:
        assert "不能为空" in str(exc)
    else:
        raise AssertionError("empty input should fail")

