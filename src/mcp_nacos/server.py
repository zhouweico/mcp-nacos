"""Nacos MCP Server

提供与 Nacos 配置中心交互的 MCP 工具。
支持 Nacos 3.x 版本。
"""

import json
import logging
import os
from enum import Enum
from typing import Any, Optional, cast

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from .auth import TokenAuthMiddleware
from .client import get_nacos_client

logger = logging.getLogger(__name__)

# 创建 MCP Server
mcp = FastMCP("nacos_mcp")


class ResponseFormat(str, Enum):
    """响应格式"""

    MARKDOWN = "markdown"
    JSON = "json"


class ConfigType(str, Enum):
    """配置类型"""

    TEXT = "text"
    JSON = "json"
    YAML = "yaml"
    XML = "xml"
    PROPERTIES = "properties"
    HTML = "html"
    TOML = "toml"


class GetConfigInput(BaseModel):
    """获取配置的输入参数"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    data_id: str = Field(
        ...,
        description="配置 ID，如 'application.yaml'、'user-service.yml'",
        min_length=1,
        max_length=256,
    )
    group_name: str = Field(
        default="DEFAULT_GROUP",
        description="配置分组，默认 DEFAULT_GROUP",
        min_length=1,
        max_length=128,
    )
    namespace_id: Optional[str] = Field(
        default=None,
        description=(
            "命名空间 ID，如 'dev'、'prod'。"
            "优先级：工具参数 > 环境变量 NACOS_NAMESPACE > 默认 public"
        ),
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式：markdown 或 json",
    )


class PublishConfigInput(BaseModel):
    """发布配置的输入参数"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    data_id: str = Field(
        ...,
        description="配置 ID，如 'application.yaml'",
        min_length=1,
        max_length=256,
    )
    group_name: str = Field(
        default="DEFAULT_GROUP",
        description="配置分组",
        min_length=1,
        max_length=128,
    )
    namespace_id: Optional[str] = Field(
        default=None,
        description="命名空间 ID，优先级：工具参数 > 环境变量 NACOS_NAMESPACE > 默认 public",
    )
    content: str = Field(
        ...,
        description="配置内容",
        min_length=1,
    )
    config_type: ConfigType = Field(
        default=ConfigType.YAML,
        description="配置类型：yaml, json, properties, text 等",
    )
    desc: Optional[str] = Field(
        default=None,
        description="配置描述",
    )


def handle_error(e: Exception) -> str:
    """统一错误处理"""
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 401:
            return "错误：认证失败，请检查 NACOS_USERNAME 和 NACOS_PASSWORD"
        elif status == 403:
            return "错误：权限不足，无法执行此操作"
        elif status == 404:
            return "错误：配置不存在，请检查 dataId 和 groupName 是否正确"
        return f"错误：Nacos API 请求失败，状态码 {status}"
    elif isinstance(e, httpx.TimeoutException):
        return "错误：请求超时，请检查 Nacos 服务是否可用"
    elif isinstance(e, httpx.ConnectError):
        return "错误：无法连接到 Nacos，请检查 NACOS_HOST、NACOS_API_PORT、NACOS_CONSOLE_PORT"
    return f"错误：{type(e).__name__}: {str(e)}"


@mcp.tool(
    name="nacos_get_config",
    annotations=cast(
        Any,
        {
            "title": "获取 Nacos 配置",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    ),
)
async def nacos_get_config(params: GetConfigInput) -> str:
    """获取 Nacos 配置内容。

    从 Nacos 配置中心获取指定的配置内容。

    参数：
        params: 包含以下内容的验证输入参数：
            - data_id: 配置 ID
            - group_name: 配置分组，默认 DEFAULT_GROUP
            - namespace_id: 命名空间 ID，可选
            - response_format: 输出格式，markdown 或 json

    返回：
        配置内容（Markdown 或 JSON 格式）
    """
    try:
        nacos_client = await get_nacos_client()
        data = await nacos_client.get_config(
            data_id=params.data_id,
            group_name=params.group_name,
            namespace_id=params.namespace_id,
        )

        # 配置不存在
        if not data or not data.get("content"):
            ns = params.namespace_id or nacos_client.default_namespace
            return f"配置不存在：dataId={params.data_id}, group={params.group_name}, namespace={ns}"

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(
                {
                    "data_id": data.get("dataId"),
                    "group_name": data.get("groupName"),
                    "namespace_id": data.get("namespaceId"),
                    "content": data.get("content"),
                    "type": data.get("type"),
                    "md5": data.get("md5"),
                },
                ensure_ascii=False,
                indent=2,
            )

        # Markdown 格式
        content = data.get("content", "")
        config_type = data.get("type", "text")
        md5 = data.get("md5", "")[:8] + "..." if data.get("md5") else ""

        lines = [
            "# 配置内容",
            "",
            "| 属性 | 值 |",
            "|------|-----|",
            f"| Data ID | {data.get('dataId')} |",
            f"| Group | {data.get('groupName')} |",
            f"| Namespace | {data.get('namespaceId')} |",
            f"| Type | {config_type} |",
            f"| MD5 | {md5} |",
            "",
            "## 内容",
            "",
            f"```{config_type}",
            content,
            "```",
        ]
        return "\n".join(lines)

    except Exception as e:
        return handle_error(e)


# 只读模式检查
_read_only = os.getenv("NACOS_READ_ONLY", "false").lower() == "true"

if not _read_only:

    @mcp.tool(
        name="nacos_publish_config",
        annotations=cast(
            Any,
            {
                "title": "发布 Nacos 配置",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            },
        ),
    )
    async def nacos_publish_config(params: PublishConfigInput) -> str:
        """发布 Nacos 配置。

        创建新配置或更新已有配置。

        参数：
            params: 包含以下内容的验证输入参数：
                - data_id: 配置 ID
                - group_name: 配置分组，默认 DEFAULT_GROUP
                - namespace_id: 命名空间 ID，可选
                - content: 配置内容
                - config_type: 配置类型，默认 yaml
                - desc: 配置描述，可选

        返回：
            发布结果
        """
        try:
            nacos_client = await get_nacos_client()
            success = await nacos_client.publish_config(
                data_id=params.data_id,
                content=params.content,
                group_name=params.group_name,
                namespace_id=params.namespace_id,
                config_type=params.config_type.value,
                desc=params.desc,
            )

            if success:
                ns = params.namespace_id or nacos_client.default_namespace
                lines = [
                    "配置发布成功",
                    "",
                    "| 属性 | 值 |",
                    "|------|-----|",
                    f"| Data ID | {params.data_id} |",
                    f"| Group | {params.group_name} |",
                    f"| Namespace | {ns} |",
                    f"| Type | {params.config_type.value} |",
                ]
                return "\n".join(lines)
            else:
                return "配置发布失败：未知原因"

        except Exception as e:
            return handle_error(e)


def _normalize_transport(raw: Optional[str]) -> str:
    """归一化传输协议名称。

    支持：stdio（默认）、sse、streamable-http。
    """
    value = (raw or "stdio").strip().lower().replace("_", "-")
    if value in {"stdio"}:
        return "stdio"
    if value in {"sse"}:
        return "sse"
    if value in {"streamable-http", "streamablehttp", "http"}:
        return "streamable-http"
    raise ValueError(
        f"不支持的 MCP_TRANSPORT: {raw!r}，仅支持 stdio、sse、streamable-http"
    )


def _run_http(transport: str) -> None:
    """以 HTTP 方式（sse / streamable-http）运行，并按需启用 Token 认证。"""
    import uvicorn

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))

    # 同步 FastMCP 内部设置，保证其构造的路由使用一致的 host/port
    mcp.settings.host = host
    mcp.settings.port = port

    if transport == "sse":
        app: Any = mcp.sse_app()
        endpoint = "/sse"
    else:
        app = mcp.streamable_http_app()
        endpoint = "/mcp"

    token = os.getenv("MCP_AUTH_TOKEN")
    if token:
        app = TokenAuthMiddleware(app, token)
        logger.info("HTTP 接口认证已启用（需携带 Authorization: Bearer <token>）")
    else:
        logger.warning(
            "MCP_AUTH_TOKEN 未设置，HTTP 接口处于无鉴权状态，"
            "生产环境请务必配置该变量"
        )

    log_level = os.getenv("MCP_LOG_LEVEL", "info").lower()
    logger.info(
        "MCP Server 启动：transport=%s, 监听 http://%s:%s%s",
        transport, host, port, endpoint,
    )
    uvicorn.run(app, host=host, port=port, log_level=log_level)


def main() -> None:
    """MCP Server 入口点。

    通过环境变量 MCP_TRANSPORT 选择传输协议：
        - stdio（默认）：标准输入输出，适合本地 AI 客户端集成
        - sse：Server-Sent Events HTTP 传输
        - streamable-http：Streamable HTTP 传输

    HTTP 传输相关环境变量：
        - MCP_HOST：监听地址，默认 0.0.0.0
        - MCP_PORT：监听端口，默认 8000
        - MCP_AUTH_TOKEN：设置后启用 Bearer Token 认证
        - MCP_LOG_LEVEL：日志级别，默认 info
    """
    logging.basicConfig(
        level=os.getenv("MCP_LOG_LEVEL", "info").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    transport = _normalize_transport(os.getenv("MCP_TRANSPORT"))
    if transport == "stdio":
        mcp.run(transport="stdio")
        return

    _run_http(transport)


if __name__ == "__main__":
    main()
