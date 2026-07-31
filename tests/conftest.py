"""共享测试夹具：将 httpx.AsyncClient 重定向到 MockTransport。"""

import httpx2 as httpx
import pytest


@pytest.fixture
def http_mock(monkeypatch):
    """返回 set_handler(fn)，fn 签名：(request) -> httpx.Response。

    预置 `NACOS_BASE_URL=http://localhost:8848` 与 `NACOS_NAMESPACE=public`，
    并移除 NACOS_USERNAME / NACOS_PASSWORD，避免触发登录流程。
    """
    monkeypatch.setenv("NACOS_BASE_URL", "http://localhost:8848")
    monkeypatch.setenv("NACOS_NAMESPACE", "public")
    monkeypatch.delenv("NACOS_USERNAME", raising=False)
    monkeypatch.delenv("NACOS_PASSWORD", raising=False)

    holder: dict = {"handler": None}
    real_async_client = httpx.AsyncClient

    def _factory(*args, **kwargs):
        if holder["handler"] is None:
            raise RuntimeError(
                "http_mock: handler not set. Call `set_handler(fn)` before using the client."
            )
        kwargs["transport"] = httpx.MockTransport(holder["handler"])
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _factory)

    def set_handler(handler):
        holder["handler"] = handler

    yield set_handler
