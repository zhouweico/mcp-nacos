"""共享测试夹具：将 httpx.AsyncClient 重定向到 MockTransport。"""

import httpx2 as httpx
import pytest


@pytest.fixture
def http_mock(monkeypatch):
    """返回一个 set_handler(fn) 函数，fn 签名为 (request) -> httpx.Response。

    客户端代码中调用的是无参的 httpx.AsyncClient()，这里统一注入 MockTransport。
    """

    holder: dict = {"handler": None}
    real_async_client = httpx.AsyncClient

    def _factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(holder["handler"])
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _factory)

    def set_handler(handler):
        holder["handler"] = handler

    yield set_handler
