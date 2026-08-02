"""Server 工具注册与调用测试。

覆盖：
- 默认只读模式（NACOS_READ_ONLY 默认 true）时 5 个写工具不注册
- 写模式（NACOS_READ_ONLY=false）时注册全部 12 个工具
- 写工具在 confirm 为 AcceptedElicitation(confirm=True) 时执行；
  confirm=False / DeclinedElicitation 时返回"已取消操作"
- confirm 参数对 AI 不可见（SDK 从 inputSchema 剔除）

写前确认由 resolver（Resolve(fn)）参数注入，工具体接收 ElicitationResult。
非交互客户端不声明 elicitation 能力时由 SDK 直接 -32021 拒绝（fail-closed），
服务端不做"放行"降级。
"""

import asyncio
import importlib
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp.server.mcpserver import AcceptedElicitation, DeclinedElicitation
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


def _make_accepted(confirm: bool) -> AcceptedElicitation:
    """构造一个 AcceptedElicitation 实例（绕过 pydantic 校验）。"""
    return AcceptedElicitation.model_construct(data=SimpleNamespace(confirm=confirm))


def _make_declined() -> DeclinedElicitation:
    return DeclinedElicitation.model_construct()


@pytest.fixture
def write_mode():
    """以写模式（NACOS_READ_ONLY=false）重载 server 模块。

    写工具仅在 READ_ONLY=false 时注册，测试写工具前需重载。
    teardown 时恢复为默认只读模式。
    """
    os.environ["NACOS_READ_ONLY"] = "false"
    importlib.reload(server)
    server.reset_nacos_client()
    try:
        yield server
    finally:
        server.reset_nacos_client()
        os.environ.pop("NACOS_READ_ONLY", None)
        importlib.reload(server)


# ==================== 工具注册 ====================


async def test_default_is_read_only():
    """默认（NACOS_READ_ONLY 未设置）时只注册只读工具。"""
    tools = await server.mcp.list_tools()
    assert {t.name for t in tools} == READONLY_TOOLS


def test_readonly_excludes_write_tools():
    """NACOS_READ_ONLY=true 时 5 个写工具均未注册。"""
    os.environ["NACOS_READ_ONLY"] = "true"
    try:
        importlib.reload(server)
        tools = asyncio.run(server.mcp.list_tools())
        assert {t.name for t in tools} == READONLY_TOOLS
    finally:
        os.environ.pop("NACOS_READ_ONLY", None)
        importlib.reload(server)


def test_write_mode_registers_all_tools(write_mode):
    """NACOS_READ_ONLY=false 时注册全部 12 个工具。"""
    tools = asyncio.run(write_mode.mcp.list_tools())
    assert {t.name for t in tools} == ALL_TOOLS


# ==================== 只读工具调用 ====================


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


async def test_missing_config_returns_not_found(monkeypatch):
    fake = AsyncMock()
    fake.default_namespace = "public"
    fake.get_config = AsyncMock(return_value={})
    monkeypatch.setattr(server, "get_nacos_client", AsyncMock(return_value=fake))

    out = await server.nacos_get_config(data_id="missing.yaml")
    text = _result_text(out)
    assert "不存在" in text


# ==================== 写工具确认路径 ====================


async def test_confirm_param_invisible(write_mode):
    """5 个写工具的 confirm 参数必须对 AI 不可见（SDK 从 inputSchema 剔除）。"""
    tools = await write_mode.mcp.list_tools()
    for tool in tools:
        if tool.name in WRITE_TOOLS:
            props = (tool.input_schema or {}).get("properties", {})
            assert "confirm" not in props, f"{tool.name} 暴露了 confirm 参数"


async def test_publish_config_user_confirms_executes(write_mode, monkeypatch):
    """confirm 为 AcceptedElicitation(confirm=True) 时执行写操作。"""
    fake = AsyncMock()
    fake.default_namespace = "public"
    fake.publish_config = AsyncMock(return_value=True)
    monkeypatch.setattr(write_mode, "get_nacos_client", AsyncMock(return_value=fake))

    out = await write_mode.nacos_publish_config(
        data_id="app.yaml",
        content="foo: bar",
        confirm=_make_accepted(True),
        config_type=ConfigType.YAML,
    )
    assert "成功" in _result_text(out)
    assert out.structured_content == {
        "success": True,
        "data_id": "app.yaml",
        "group_name": "DEFAULT_GROUP",
        "namespace_id": "public",
        "type": "yaml",
    }
    fake.publish_config.assert_awaited_once()


async def test_publish_config_user_declines(write_mode, monkeypatch):
    """confirm 为 DeclinedElicitation 时返回"已取消操作"且不调用客户端。"""
    fake = AsyncMock()
    fake.default_namespace = "public"
    monkeypatch.setattr(write_mode, "get_nacos_client", AsyncMock(return_value=fake))

    out = await write_mode.nacos_publish_config(
        data_id="app.yaml",
        content="foo: bar",
        confirm=_make_declined(),
    )
    assert "已取消操作" in _result_text(out)
    fake.publish_config.assert_not_awaited()


async def test_publish_config_user_rejects_with_confirm_false(write_mode, monkeypatch):
    """confirm 为 AcceptedElicitation(confirm=False) 时返回"已取消操作"。"""
    fake = AsyncMock()
    fake.default_namespace = "public"
    monkeypatch.setattr(write_mode, "get_nacos_client", AsyncMock(return_value=fake))

    out = await write_mode.nacos_publish_config(
        data_id="app.yaml",
        content="foo: bar",
        confirm=_make_accepted(False),
    )
    assert "已取消操作" in _result_text(out)
    fake.publish_config.assert_not_awaited()


async def test_delete_config_user_confirms_executes(write_mode, monkeypatch):
    """delete_config 在确认后执行删除。"""
    fake = AsyncMock()
    fake.default_namespace = "public"
    fake.delete_config = AsyncMock(return_value=True)
    monkeypatch.setattr(write_mode, "get_nacos_client", AsyncMock(return_value=fake))

    out = await write_mode.nacos_delete_config(
        data_id="app.yaml",
        confirm=_make_accepted(True),
    )
    assert "成功" in _result_text(out)
    assert out.structured_content == {
        "success": True,
        "data_id": "app.yaml",
        "group_name": "DEFAULT_GROUP",
        "namespace_id": "public",
    }
    fake.delete_config.assert_awaited_once()


async def test_create_namespace_user_confirms_executes(write_mode, monkeypatch):
    """create_namespace 在确认后执行创建。"""
    fake = AsyncMock()
    fake.default_namespace = "public"
    fake.create_namespace = AsyncMock(return_value=True)
    monkeypatch.setattr(write_mode, "get_nacos_client", AsyncMock(return_value=fake))

    out = await write_mode.nacos_create_namespace(
        namespace_id="dev",
        namespace_name="开发环境",
        confirm=_make_accepted(True),
    )
    assert "成功" in _result_text(out)
    assert out.structured_content == {
        "success": True,
        "namespace_id": "dev",
        "namespace_name": "开发环境",
    }
    fake.create_namespace.assert_awaited_once()


async def test_update_namespace_user_confirms_executes(write_mode, monkeypatch):
    """update_namespace 在确认后执行更新。"""
    fake = AsyncMock()
    fake.default_namespace = "public"
    fake.update_namespace = AsyncMock(return_value=True)
    monkeypatch.setattr(write_mode, "get_nacos_client", AsyncMock(return_value=fake))

    out = await write_mode.nacos_update_namespace(
        namespace_id="dev",
        namespace_name="开发环境-更新",
        confirm=_make_accepted(True),
    )
    assert "成功" in _result_text(out)
    assert out.structured_content == {
        "success": True,
        "namespace_id": "dev",
        "namespace_name": "开发环境-更新",
    }
    fake.update_namespace.assert_awaited_once()


async def test_delete_namespace_user_confirms_executes(write_mode, monkeypatch):
    """delete_namespace 在确认后执行删除。"""
    fake = AsyncMock()
    fake.default_namespace = "public"
    fake.delete_namespace = AsyncMock(return_value=True)
    monkeypatch.setattr(write_mode, "get_nacos_client", AsyncMock(return_value=fake))

    out = await write_mode.nacos_delete_namespace(
        namespace_id="dev",
        confirm=_make_accepted(True),
    )
    assert "成功" in _result_text(out)
    assert out.structured_content == {
        "success": True,
        "namespace_id": "dev",
    }
    fake.delete_namespace.assert_awaited_once()


async def test_delete_namespace_user_declines(write_mode, monkeypatch):
    """delete_namespace 在拒绝时不执行删除。"""
    fake = AsyncMock()
    fake.default_namespace = "public"
    monkeypatch.setattr(write_mode, "get_nacos_client", AsyncMock(return_value=fake))

    out = await write_mode.nacos_delete_namespace(
        namespace_id="dev",
        confirm=_make_declined(),
    )
    assert "已取消操作" in _result_text(out)
    fake.delete_namespace.assert_not_awaited()
