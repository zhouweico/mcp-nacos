"""端到端 MCP 协议验证（最接近真实 WorkBuddy 接入）。

启动一个本地 mock Nacos（仅返回固定 JSON），用 mcp Python SDK（2.0+ 的 Client API）
以 stdio 方式拉起 mcp-nacos server，完成 initialize -> list_tools（工具发现）->
call_tool（调用）。覆盖读工具调用、写工具发现与 fail-closed 拒绝行为。

写工具的确认路径（Elicitation）由 test_server.py 单元测试覆盖；e2e 额外验证
非交互客户端（stdio client 不声明 elicitation 能力）调用写工具时被 SDK -32021
拒绝（fail-closed），客户端侧直接抛 MCPError(-32021)。
"""

import asyncio
import http.server
import json
import os
import sys
import threading

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError

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
            return self._send(
                {
                    "code": 0,
                    "message": "",
                    "data": {
                        "dataId": "app.yaml",
                        "groupName": "DEFAULT_GROUP",
                        "namespaceId": "public",
                        "content": "server:\n  port: 8080\n",
                        "type": "yaml",
                        "md5": "abc123",
                    },
                }
            )
        if self.path.startswith("/v3/console/cs/history"):
            return self._send({"code": 0, "data": {"pageItems": [], "totalCount": 0}})
        if self.path.startswith("/v3/console/core/namespace"):
            return self._send(
                {
                    "code": 0,
                    "data": [
                        {
                            "namespace": "public",
                            "namespaceShowName": "public",
                            "quota": 200,
                            "configCount": 0,
                        },
                    ],
                }
            )
        return self._send({"code": 0, "data": True})


def _start_mock():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), _MockNacos)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _text(result):
    return "".join(getattr(c, "text", "") for c in result.content if hasattr(c, "text"))


def test_e2e_mcp_stdio():
    srv = _start_mock()
    try:
        env = dict(os.environ)
        env.update(
            {
                "NACOS_VERSION": "3",
                "NACOS_BASE_URL": f"http://127.0.0.1:{MOCK_PORT}",
                "MCP_TRANSPORT": "stdio",
                "NACOS_READ_ONLY": "false",
                # 不设用户名/密码 -> v3 不走登录，直接以无 token 访问 mock
            }
        )

        async def run():
            params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_nacos"], env=env)
            # mcp 2.0+：Client 直接包裹 stdio_client 提供的传输，自动完成 initialize
            async with Client(stdio_client(params)) as client:
                # 1) 工具发现
                list_result = await client.list_tools()
                tools = list_result.tools
                names = {t.name for t in tools}
                assert "nacos_get_config" in names, "工具发现缺失 nacos_get_config"
                assert "nacos_publish_config" in names, "工具发现缺失 nacos_publish_config"

                # 2) 调用读工具
                res_get = await client.call_tool(
                    "nacos_get_config",
                    {"data_id": "app.yaml", "group_name": "DEFAULT_GROUP"},
                )
                text_get = _text(res_get)
                assert "server:" in text_get, f"读工具返回异常: {text_get}"

                # 3) 工具发现数量应为 12
                assert len(names) == 12, f"预期 12 个工具，实际 {len(names)}"

                # 4) 写工具在非交互客户端（不声明 elicitation 能力）下被 fail-closed 拒绝
                #    SDK 直接抛 MCPError(-32021)，不再进入工具体
                with pytest.raises(MCPError) as exc_info:
                    await client.call_tool(
                        "nacos_publish_config",
                        {"data_id": "app.yaml", "content": "foo: bar"},
                    )
                assert exc_info.value.code == -32021, (
                    f"预期错误码 -32021，实际: {exc_info.value.code}"
                )

        asyncio.run(run())
    finally:
        srv.shutdown()
