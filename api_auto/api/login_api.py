# Author:HankQueen
# Date:2026/9/18
import logging
from api_auto.api.base_api import BaseApi

logger = logging.getLogger(__name__)


class LoginApi(BaseApi):

    def get_captcha(self) -> dict:
        """
        获取验证码
        """
        resp = self.get("/base/admin/verifyCode")
        assert resp.status_code == 200, f"获取验证码失败: {resp.text}"
        return resp.json()

    def login(self, username: str, password_md5: str,
              captcha: str, request_id: str):
        """
        登录
        """
        resp = self.post("/base/admin/login", json={
            "userName": username,
            "password": password_md5,
            "captcha": captcha,
            "requestId": request_id
        })
        assert resp.status_code == 200, f"登录失败: {resp.text}"
        logger.info(f"登录成功 Cookie: {dict(self.session.cookies)}")
        return resp

    def set_csrf_token(self):
        """
        登录成功后把 Csrf-Token 设置到请求头
        """
        csrf_token = self.session.cookies.get("Csrf-Token")
        if csrf_token:
            self.session.headers.update({"Csrf-Token": csrf_token})
            logger.info(f"Csrf-Token 已设置: {csrf_token}")
        else:
            logger.warning("未找到 Csrf-Token")