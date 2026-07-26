"""端到端 MCP 协议验证（最接近真实 WorkBuddy 接入）。

启动一个本地 mock Nacos（仅返回固定 JSON），用 mcp Python SDK 以 stdio 方式拉起
mcp-nacos server，完成 initialize -> list_tools（工具发现）-> call_tool（调用）。
覆盖一个读工具与一个写工具，验证 MCP 装配、工具发现与真实调用链路。
"""

import asyncio
import http.server
import json
import os
import sys
import threading

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

MOCK_PORT = 8099


class _MockNacos(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        # 登录 or 写操作，统一返回成功
        if self.path.endswith("/auth/user/login"):
            return self._send({"accessToken": "tok", "tokenTtl": 18000})
        return self._send({"code": 0, "message": "", "data": True})

    def do_GET(self):
        if self.path.startswith("/v3/console/cs/config"):
            return self._send({"code": 0, "message": "", "data": {
                "dataId": "app.yaml", "groupName": "DEFAULT_GROUP", "namespaceId": "public",
                "content": "server:\n  port: 8080\n", "type": "yaml", "md5": "abc123",
            }})
        if self.path.startswith("/v3/console/cs/history"):
            return self._send({"code": 0, "data": {"pageItems": [], "totalCount": 0}})
        if self.path.startswith("/v3/console/core/namespace"):
            return self._send({"code": 0, "data": [
                {"namespace": "public", "namespaceShowName": "public", "quota": 200, "configCount": 0},
            ]})
        return self._send({"code": 0, "data": True})


def _start_mock():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), _MockNacos)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_e2e_mcp_stdio():
    srv = _start_mock()
    try:
        env = dict(os.environ)
        env.update({
            "NACOS_VERSION": "3",
            "NACOS_HOST": "127.0.0.1",
            "NACOS_API_PORT": str(MOCK_PORT),
            "NACOS_CONSOLE_PORT": str(MOCK_PORT),
            "MCP_TRANSPORT": "stdio",
            # 不设用户名/密码 -> v3 不走登录，直接以无 token 访问 mock
        })

        async def run():
            params = StdioServerParameters(
                command=sys.executable, args=["-m", "mcp_nacos"], env=env)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # 1) 工具发现
                    list_result = await session.list_tools()
                    tools = list_result.tools
                    names = {t.name for t in tools}
                    assert "nacos_get_config" in names, "工具发现缺失 nacos_get_config"
                    assert "nacos_publish_config" in names, "工具发现缺失 nacos_publish_config"

                    # 2) 调用读工具
                    res_get = await session.call_tool(
                        "nacos_get_config",
                        {"data_id": "app.yaml", "group_name": "DEFAULT_GROUP"},
                    )
                    text_get = res_get.content[0].text
                    assert "server:" in text_get, f"读工具返回异常: {text_get}"

                    # 3) 调用写工具
                    res_pub = await session.call_tool(
                        "nacos_publish_config",
                        {"data_id": "app2.yaml", "content": "foo: bar", "config_type": "yaml"},
                    )
                    text_pub = res_pub.content[0].text
                    assert "成功" in text_pub, f"写工具返回异常: {text_pub}"

                    # 4) 工具发现数量应为 11
                    assert len(names) == 11, f"预期 11 个工具，实际 {len(names)}"

        asyncio.run(run())
    finally:
        srv.shutdown()
