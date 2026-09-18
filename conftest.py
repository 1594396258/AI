# Author:HankQueen
# Date:2026/9/17
import pytest
from api_auto.api.base_api import BaseApi
from api_auto.api.login_api import LoginApi
from api_auto.utils.data_loader import load_config
from api_auto.utils.encrypt import encrypt_password

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

@pytest.fixture(scope="session")
def auth_api(config):
    api = LoginApi(
        base_url=config["base_url"],
        timeout=config["timeout"]
    )
    # 第一步：获取验证码
    captcha_resp = api.get_captcha()
    data = captcha_resp.get("dataObj", captcha_resp)
    request_id = data.get("requestId")
    # 第二步：暂时用固定验证码，后续让开发关闭或提供万能验证码
    captcha = "7j7y"

    # 第三步：加密密码
    password_md5 = encrypt_password(
        username=config["username"],
        plain_password=config["password"]
    )

    # 第四步：登录
    api.login(
        username=config["username"],
        password_md5=password_md5,
        captcha=captcha,
        request_id=request_id
    )

    # 第五步：设置 Csrf-Token
    api.set_csrf_token()

    return api