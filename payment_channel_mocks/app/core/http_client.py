from __future__ import annotations

from typing import Any

import requests


class HttpClient:
    """Outbound HTTP wrapper; it deliberately does not log raw test credentials."""

    def __init__(self, timeout: float = 10):
        self.timeout = timeout

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        # Callback is an explicit operation. Do not follow redirects or retry it.
        kwargs.setdefault("allow_redirects", False)
        return requests.request(method, url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("DELETE", url, **kwargs)
