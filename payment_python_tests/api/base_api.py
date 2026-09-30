from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import requests

from payment_python_tests.utils.redact_utils import redact


logger = logging.getLogger(__name__)


class BaseApi:
    """Reusable HTTP client base for API test clients."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10,
        *,
        session: requests.Session | None = None,
        default_headers: dict[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.session = session or requests.Session()
        if default_headers:
            self.session.headers.update(default_headers)

    def set_header(self, name: str, value: str) -> None:
        self.session.headers.update({name: value})

    def set_token(self, token: str, scheme: str = "Bearer") -> None:
        self.set_header("Authorization", f"{scheme} {token}".strip())

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = urljoin(self.base_url, path.lstrip("/"))
        timeout = kwargs.pop("timeout", self.timeout)
        log_data = {
            "method": method.upper(),
            "url": url,
            "params": kwargs.get("params"),
            "json": kwargs.get("json"),
            "headers": kwargs.get("headers"),
        }
        logger.info("HTTP request: %s", redact(log_data))
        response = self.session.request(method=method.upper(), url=url, timeout=timeout, **kwargs)
        try:
            response_log: Any = redact(response.json())
        except (ValueError, TypeError):
            response_log = response.text[:500]
        logger.info(
            "HTTP response: method=%s url=%s status=%s body=%s",
            method.upper(),
            url,
            response.status_code,
            response_log,
        )
        return response

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("DELETE", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("PATCH", path, **kwargs)

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "BaseApi":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
