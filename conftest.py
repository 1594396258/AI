# Author:HankQueen
# Date:2026/9/17
import pytest
from api_auto.api.base_api import BaseApi
from api_auto.utils.data_loader import load_config


@pytest.fixture(scope="session")
def config():
    return load_config("test")


@pytest.fixture(scope="session")
def base_api(config):
    api = BaseApi(
        base_url=config["base_url"],
        timeout=config["timeout"]
    )

    # # 登录
    # resp = api.post("/login", json={
    #     "username": config["username"],
    #     "password": config["password"]
    # })
    #
    # assert resp.status_code == 200, f"登录失败: {resp.text}"
    #
    # # Cookie：session 已经自动保存，不需要额外处理
    #
    # # Token：手动取出来设置到 session headers
    # token = resp.json().get("token")
    # if token:
    #     api.set_token(token)

    return api