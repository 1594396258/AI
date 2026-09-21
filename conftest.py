# Author:HankQueen
# Date:2026/9/17
import pytest
from api_auto.api.base_api import BaseApi
from api_auto.api.login_api import LoginApi
from api_auto.utils.data_loader import load_config
from api_auto.utils.encrypt import encrypt_password
from api_auto.utils.redis_helper import get_captcha_from_redis
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
    request_id = captcha_resp.get("requestId")
    # 第二步：从 Redis 获取验证码原文
    captcha =get_captcha_from_redis(request_id)
    assert captcha, f"从 Redis 获取验证码失败, requestId={request_id}"
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

@pytest.fixture(scope="session", autouse=True)
def login(auth_api):
    """
    session 级别自动登录，所有用例执行前自动触发
    """
    pass