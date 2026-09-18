# Author:HankQueen
# Date:2026/9/17
import requests
import logging

logger = logging.getLogger(__name__)


class BaseApi:
    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()

    def set_token(self, token: str):
        """
        登录后把 token 设置到 session headers
        后续所有请求自动带上
        """
        self.session.headers.update({
            "Authorization": f"Bearer {token}"
        })
        logger.info("token 已设置到 session headers")

    def get(self, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        logger.info(f"GET {url} params={kwargs.get('params')}")
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        logger.info(f"响应状态码: {resp.status_code}")
        logger.info(f"响应内容: {resp.text[:200]}")
        return resp

    def post(self, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        logger.info(f"POST {url} body={kwargs.get('json')}")
        resp = self.session.post(url, timeout=self.timeout, **kwargs)
        logger.info(f"响应状态码: {resp.status_code}")
        logger.info(f"响应内容: {resp.text[:200]}")
        return resp

    def put(self, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        logger.info(f"PUT {url} body={kwargs.get('json')}")
        resp = self.session.put(url, timeout=self.timeout, **kwargs)
        logger.info(f"响应状态码: {resp.status_code}")
        return resp

    def delete(self, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        logger.info(f"DELETE {url}")
        resp = self.session.delete(url, timeout=self.timeout, **kwargs)
        logger.info(f"响应状态码: {resp.status_code}")
        return resp