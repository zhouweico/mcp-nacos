"""Server 工具注册与调用测试。"""

import asyncio
import importlib
import os
from unittest.mock import AsyncMock

from mcp.types import CallToolResult

from mcp_nacos import server
from mcp_nacos.server import ConfigType

ALL_TOOLS = {
    "nacos_get_config",
    "nacos_list_config_history",
    "nacos_get_config_history",
    "nacos_get_config_previous",
    "nacos_list_configs",
    "nacos_list_namespaces",
    "nacos_get_namespace",
    "nacos_publish_config",
    "nacos_delete_config",
    "nacos_create_namespace",
    "nacos_update_namespace",
    "nacos_delete_namespace",
}
WRITE_TOOLS = {
    "nacos_publish_config",
    "nacos_delete_config",
    "nacos_create_namespace",
    "nacos_update_namespace",
    "nacos_delete_namespace",
}
READONLY_TOOLS = ALL_TOOLS - WRITE_TOOLS


def _result_text(result: object) -> str:
    """从工具返回值中提取文本（兼容 str 和 CallToolResult）。"""
    if isinstance(result, str):
        return result
    if isinstance(result, CallToolResult):
        return "".join(getattr(c, "text", "") for c in result.content if hasattr(c, "text"))
    return str(result)


async def test_default_registers_all_tools():
    tools = await server.mcp.list_tools()
    assert {t.name for t in tools} == ALL_TOOLS


def test_readonly_registers_only_read_tools():
    os.environ["NACOS_READ_ONLY"] = "true"
    try:
        importlib.reload(server)
        tools = asyncio.run(server.mcp.list_tools())
        assert {t.name for t in tools} == READONLY_TOOLS
    finally:
        os.environ.pop("NACOS_READ_ONLY", None)
        importlib.reload(server)


async def test_invoke_get_config(monkeypatch):
    fake = AsyncMock()
    fake.default_namespace = "public"
    fake.get_config = AsyncMock(
        return_value={
            "dataId": "app.yaml",
            "groupName": "DEFAULT_GROUP",
            "namespaceId": "public",
            "content": "server:\n  port: 8080\n",
            "type": "yaml",
            "md5": "abc123",
        }
    )
    monkeypatch.setattr(server, "get_nacos_client", AsyncMock(return_value=fake))

    out = await server.nacos_get_config(data_id="app.yaml")
    text = _result_text(out)
    assert "server:" in text and "app.yaml" in text


async def test_invoke_list_configs(monkeypatch):
    fake = AsyncMock()
    fake.default_namespace = "public"
    fake.list_configs = AsyncMock(
        return_value={
            "total": 2,
            "configs": [
                {"data_id": "app.yaml", "group_name": "DEFAULT_GROUP"},
                {"data_id": "user.yaml", "group_name": "DEFAULT_GROUP"},
            ],
        }
    )
    monkeypatch.setattr(server, "get_nacos_client", AsyncMock(return_value=fake))

    out = await server.nacos_list_configs(namespace_id="public")
    text = _result_text(out)
    assert "app.yaml" in text and "user.yaml" in text


async def test_invoke_list_configs_filters(monkeypatch):
    fake = AsyncMock()
    fake.default_namespace = "public"
    fake.list_configs = AsyncMock(
        return_value={"total": 1, "configs": [{"data_id": "app.yaml", "group_name": "DEFAULT_GROUP"}]}
    )
    monkeypatch.setattr(server, "get_nacos_client", AsyncMock(return_value=fake))

    # v1/v2 支持按 data_id 过滤并透传全部参数
    out = await server.nacos_list_configs(namespace_id="dev", data_id="app", page_size=20)
    text = _result_text(out)
    assert "app.yaml" in text
    fake.list_configs.assert_awaited_once_with(
        namespace_id="dev",
        data_id="app",
        group_name=None,
        app_name=None,
        config_tags=None,
        search="blur",
        page_no=1,
        page_size=20,
    )


async def test_invoke_publish_config(monkeypatch):
    fake = AsyncMock()
    fake.default_namespace = "public"
    fake.publish_config = AsyncMock(return_value=True)
    monkeypatch.setattr(server, "get_nacos_client", AsyncMock(return_value=fake))

    out = await server.nacos_publish_config(data_id="app.yaml", content="foo: bar", config_type=ConfigType.YAML)
    assert "成功" in out


async def test_missing_config_returns_not_found(monkeypatch):
    fake = AsyncMock()
    fake.default_namespace = "public"
    fake.get_config = AsyncMock(return_value={})
    monkeypatch.setattr(server, "get_nacos_client", AsyncMock(return_value=fake))

    out = await server.nacos_get_config(data_id="missing.yaml")
    text = _result_text(out)
    assert "不存在" in text
