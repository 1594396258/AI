import pytest


@pytest.mark.parametrize(
    ("channel_status", "expected_local_state"),
    [
        ("pending", "PROCESSING"),
        ("success", "SUCCESS"),
        ("failed", "FAIL"),
    ],
)
def test_channel_status_matrix_is_explicit(channel_status, expected_local_state):
    """这是状态契约示例，接入数据库/回调 Mock 后替换为真实断言。"""
    assert channel_status
    assert expected_local_state in {"PROCESSING", "SUCCESS", "FAIL"}
