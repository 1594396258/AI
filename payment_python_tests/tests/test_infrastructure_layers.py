from __future__ import annotations

from payment_python_tests.cache.redis_client import RedisClient
from payment_python_tests.config.settings import load_settings
from payment_python_tests.database.mysql_client import MysqlClient
from payment_python_tests.database.order_repository import OrderRepository


class FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None):
        self.values[key] = value
        return True

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)

    def exists(self, key):
        return int(key in self.values)


class FakeMysql:
    def __init__(self, row=None):
        self.row = row
        self.calls = []

    def query_one(self, sql, params):
        self.calls.append((sql, params))
        return self.row


def test_settings_load_yaml_defaults_and_environment_overrides(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        "test:\n"
        "  payment:\n"
        "    base_url: http://yaml.example/v1\n"
        "    timeout: 9\n"
        "  database:\n"
        "    port: 3307\n"
        "  redis:\n"
        "    port: 6380\n"
        "  ai:\n"
        "    base_url: http://ai.example/v1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MCH_ID", "merchant-1")
    monkeypatch.setenv("PAYMENT_BASE_URL", "http://env.example/v1")

    settings = load_settings("test", config)

    assert settings.payment.base_url == "http://env.example/v1"
    assert settings.payment.timeout == 9
    assert settings.merchant.merchant_id == "merchant-1"
    assert settings.database.port == 3307
    assert settings.redis.port == 6380


def test_mysql_client_blocks_writes_by_default():
    client = MysqlClient.__new__(MysqlClient)
    client.allow_write = False

    try:
        client.execute("DELETE FROM FIN_PAY_ORDER")
    except PermissionError as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("read-only MysqlClient accepted a write")


def test_order_repository_maps_database_row():
    mysql = FakeMysql(
        {
            "ORDER_NO": "o-1",
            "OUT_ORDER_NO": "m-1",
            "TRADE_STATE": 2,
            "TRANSACTION_ID": "t-1",
            "AMOUNT": 10000,
            "CHANNEL_AMOUNT": 10000,
            "NOTIFY_STATE": 1,
        }
    )
    order = OrderRepository(mysql).get_by_out_order_no("m-1")

    assert order.order_no == "o-1"
    assert order.state_name == "SUCCESS"
    assert mysql.calls[0][1] == ("m-1",)


def test_redis_client_applies_prefix_and_json_encoding():
    cache = RedisClient.__new__(RedisClient)
    cache.key_prefix = "payment-auto:"
    cache.client = FakeRedis()

    cache.set_json("order:o-1", {"status": "SUCCESS"})

    assert cache.exists("order:o-1")
    assert cache.get_json("order:o-1") == {"status": "SUCCESS"}
    assert "payment-auto:order:o-1" in cache.client.values
