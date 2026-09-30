from payment_python_tests.utils.sign_utils import hmac_sha256_sorted_values
from payment_python_tests.utils.wait_utils import wait_until


def test_hmac_is_deterministic():
    assert hmac_sha256_sorted_values({"b": "2", "a": "1", "hash": "ignored"}, "secret") == hmac_sha256_sorted_values({"a": "1", "b": "2"}, "secret")


def test_wait_until_returns_without_fixed_sleep():
    values = iter(["PROCESSING", "SUCCESS"])
    result = wait_until(lambda: next(values), lambda value: value == "SUCCESS", timeout=1, interval=0)
    assert result == "SUCCESS"
