"""TokenAuthMiddleware 测试。"""

from mcp_nacos.auth import TokenAuthMiddleware


async def _call(mw, path, headers):
    scope = {
        "type": "http",
        "path": path,
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
    }
    sent = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.update(message)

    await mw(scope, receive, send)
    return sent


async def ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def test_no_token_returns_401():
    mw = TokenAuthMiddleware(ok_app, "secret")
    sent = await _call(mw, "/mcp", {})
    assert sent["status"] == 401


async def test_valid_bearer_token_passes():
    mw = TokenAuthMiddleware(ok_app, "secret")
    sent = await _call(mw, "/mcp", {"Authorization": "Bearer secret"})
    assert sent["status"] == 200


async def test_x_auth_token_passes():
    mw = TokenAuthMiddleware(ok_app, "secret")
    sent = await _call(mw, "/mcp", {"X-Auth-Token": "secret"})
    assert sent["status"] == 200


async def test_wrong_token_returns_401():
    mw = TokenAuthMiddleware(ok_app, "secret")
    sent = await _call(mw, "/mcp", {"Authorization": "Bearer wrong"})
    assert sent["status"] == 401


async def test_health_bypasses_auth():
    mw = TokenAuthMiddleware(ok_app, "secret")
    sent = await _call(mw, "/health", {})
    assert sent["status"] == 200
