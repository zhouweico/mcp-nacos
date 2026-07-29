"""Nacos MCP Server

提供与 Nacos 配置中心交互的 MCP 工具。
支持 Nacos 1.x / 2.x / 3.x（默认 3.x，由 NACOS_VERSION 决定）。

所有工具的最新说明见各工具 docstring；工具入参均为扁平字段（非嵌套对象），
便于 MCP 客户端与 LLM 直接填充。
"""

import json
import logging
import os
from enum import Enum
from typing import Annotated, Any, Optional, cast

import httpx
from mcp.server import MCPServer
from pydantic import Field

from .auth import TokenAuthMiddleware
from .client import get_nacos_client

logger = logging.getLogger(__name__)

# 创建 MCP Server
mcp = MCPServer("nacos_mcp")


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


def _ro(title: str) -> Any:
    """只读工具注解"""
    return cast(
        Any,
        {
            "title": title,
            "read_only_hint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )


def _rw(title: str, destructive: bool = False, idempotent: bool = False) -> Any:
    """写工具注解"""
    return cast(
        Any,
        {
            "title": title,
            "read_only_hint": False,
            "destructiveHint": destructive,
            "idempotentHint": idempotent,
            "openWorldHint": True,
        },
    )


def _to_json(data: Any) -> str:
    """将对象序列化为可读 JSON 字符串"""
    return json.dumps(data, ensure_ascii=False, indent=2)


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


@mcp.tool(name="nacos_get_config", annotations=_ro("获取 Nacos 配置"))
async def nacos_get_config(
    data_id: Annotated[
        str,
        Field(
            description="配置 ID，如 'application.yaml'、'user-service.yml'",
            min_length=1,
            max_length=256,
        ),
    ],
    group_name: Annotated[
        str, Field(description="配置分组，默认 DEFAULT_GROUP", min_length=1, max_length=128)
    ] = "DEFAULT_GROUP",
    namespace_id: Annotated[
        Optional[str],
        Field(
            description=(
                "命名空间 ID（如 dev/prod）；优先级：工具参数 > "
                "NACOS_NAMESPACE 环境变量 > 默认 public"
            )
        ),
    ] = None,
    response_format: Annotated[
        ResponseFormat, Field(description="输出格式：markdown 或 json")
    ] = ResponseFormat.MARKDOWN,
) -> str:
    """获取 Nacos 配置内容（2.1，只读）。

    对应 Nacos OpenAPI：
    - v1：GET /nacos/v1/cs/configs（参数 tenant）
    - v2：GET /nacos/v2/cs/config（参数 namespaceId）
    - v3：GET /v3/console/cs/config（Console API，端口 8080）

    按 dataId + group + namespace 唯一定位配置，返回配置内容。
    """
    try:
        nacos_client = await get_nacos_client()
        data = await nacos_client.get_config(
            data_id=data_id,
            group_name=group_name,
            namespace_id=namespace_id,
        )

        # 配置不存在
        if not data or not data.get("content"):
            ns = namespace_id or nacos_client.default_namespace
            return f"配置不存在：dataId={data_id}, group={group_name}, namespace={ns}"

        if response_format == ResponseFormat.JSON:
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


@mcp.tool(name="nacos_list_config_history", annotations=_ro("查询配置历史版本列表"))
async def nacos_list_config_history(
    data_id: Annotated[str, Field(description="配置 ID", min_length=1, max_length=256)],
    group_name: Annotated[
        str, Field(description="配置分组，默认 DEFAULT_GROUP", min_length=1, max_length=128)
    ] = "DEFAULT_GROUP",
    namespace_id: Annotated[Optional[str], Field(description="命名空间 ID，可选")] = None,
    page_no: Annotated[int, Field(description="页码，默认 1", ge=1)] = 1,
    page_size: Annotated[int, Field(description="每页条数，默认 100", ge=1, le=500)] = 100,
) -> str:
    """查询配置历史版本列表（2.14，只读）。

    对应 Nacos OpenAPI：
    - v1：GET /nacos/v1/cs/history
    - v2：GET /nacos/v2/cs/history/list
    - v3：GET /v3/console/cs/history/list（Console API）

    返回分页的历史版本列表（id、opType、操作人、时间等）。
    """
    try:
        nacos_client = await get_nacos_client()
        data = await nacos_client.list_config_history(
            data_id=data_id,
            group_name=group_name,
            namespace_id=namespace_id,
            page_no=page_no,
            page_size=page_size,
        )
        return _to_json(data)
    except Exception as e:
        return handle_error(e)


@mcp.tool(name="nacos_get_config_history", annotations=_ro("查询具体历史版本配置"))
async def nacos_get_config_history(
    nid: Annotated[int, Field(description="历史版本 ID（nid），必填", ge=0)],
    data_id: Annotated[str, Field(description="配置 ID", min_length=1, max_length=256)],
    group_name: Annotated[
        str, Field(description="配置分组，默认 DEFAULT_GROUP", min_length=1, max_length=128)
    ] = "DEFAULT_GROUP",
    namespace_id: Annotated[Optional[str], Field(description="命名空间 ID，可选")] = None,
) -> str:
    """查询某次历史变更记录（2.15，只读）。

    对应 Nacos OpenAPI：
    - v1：GET /nacos/v1/cs/history
    - v2：GET /nacos/v2/cs/history
    - v3：GET /v3/console/cs/history（Console API）

    按历史记录 ID（nid）返回该次变更的完整配置内容。
    """
    try:
        nacos_client = await get_nacos_client()
        data = await nacos_client.get_config_history(
            nid=nid,
            data_id=data_id,
            group_name=group_name,
            namespace_id=namespace_id,
        )
        return _to_json(data)
    except Exception as e:
        return handle_error(e)


@mcp.tool(name="nacos_get_config_previous", annotations=_ro("查询配置上一版本"))
async def nacos_get_config_previous(
    config_id: Annotated[
        int, Field(description="配置存储 ID（对应历史接口中的 id 字段），必填", ge=0)
    ],
    data_id: Annotated[str, Field(description="配置 ID", min_length=1, max_length=256)],
    group_name: Annotated[
        str, Field(description="配置分组，默认 DEFAULT_GROUP", min_length=1, max_length=128)
    ] = "DEFAULT_GROUP",
    namespace_id: Annotated[Optional[str], Field(description="命名空间 ID，可选")] = None,
) -> str:
    """查询配置最新状态的前一次变更历史（2.16，只读）。

    对应 Nacos OpenAPI：
    - v1：GET /nacos/v1/cs/history/previous
    - v2：GET /nacos/v2/cs/history/previous
    - v3：GET /v3/console/cs/history/previous（Console API）

    按配置存储 ID（id）返回上一版本的完整配置内容。
    """
    try:
        nacos_client = await get_nacos_client()
        data = await nacos_client.get_config_previous(
            config_id=config_id,
            data_id=data_id,
            group_name=group_name,
            namespace_id=namespace_id,
        )
        return _to_json(data)
    except Exception as e:
        return handle_error(e)


@mcp.tool(name="nacos_list_namespaces", annotations=_ro("查询命名空间列表"))
async def nacos_list_namespaces() -> str:
    """查询命名空间列表（1.7，只读）。

    对应 Nacos OpenAPI：
    - v1：GET /nacos/v1/console/namespaces
    - v2：GET /nacos/v2/console/namespace/list
    - v3：GET /v3/console/core/namespace/list（Console API）

    返回当前 Nacos 实例下的所有命名空间（含 public，及每个命名空间的配额与使用量）。
    """
    try:
        nacos_client = await get_nacos_client()
        data = await nacos_client.list_namespaces()
        return _to_json(data)
    except Exception as e:
        return handle_error(e)


@mcp.tool(name="nacos_get_namespace", annotations=_ro("查询单个命名空间"))
async def nacos_get_namespace(
    namespace_id: Annotated[
        str,
        Field(
            description="命名空间 ID。优先级：工具参数 > 环境变量 NACOS_NAMESPACE > 默认 public",
            min_length=1,
        ),
    ],
) -> str:
    """查询单个命名空间详情（1.8，只读）。

    对应 Nacos OpenAPI：
    - v1：官方无单查接口，由命名空间列表过滤模拟
    - v2：GET /nacos/v2/console/namespace
    - v3：GET /v3/console/core/namespace（Console API）

    按 namespace_id 返回该命名空间的配额、使用量等详情。
    """
    try:
        nacos_client = await get_nacos_client()
        data = await nacos_client.get_namespace(namespace_id=namespace_id)
        return _to_json(data)
    except Exception as e:
        return handle_error(e)


# 只读模式检查
_read_only = os.getenv("NACOS_READ_ONLY", "false").lower() == "true"

if not _read_only:

    @mcp.tool(name="nacos_publish_config", annotations=_rw("发布 Nacos 配置", idempotent=True))
    async def nacos_publish_config(
        data_id: Annotated[
            str, Field(description="配置 ID，如 'application.yaml'", min_length=1, max_length=256)
        ],
        content: Annotated[str, Field(description="配置内容", min_length=1)],
        group_name: Annotated[
            str, Field(description="配置分组，默认 DEFAULT_GROUP", min_length=1, max_length=128)
        ] = "DEFAULT_GROUP",
        namespace_id: Annotated[
            Optional[str],
            Field(description="命名空间 ID，可选，优先级：参数 > NACOS_NAMESPACE > public"),
        ] = None,
        config_type: Annotated[
            ConfigType, Field(description="配置类型：yaml, json, properties, text 等")
        ] = ConfigType.YAML,
        desc: Annotated[Optional[str], Field(description="配置描述，可选")] = None,
    ) -> str:
        """发布/更新 Nacos 配置（创建或覆盖已有配置，发布即生效）。

        对应 Nacos OpenAPI：
        - v1：POST /nacos/v1/cs/configs（参数 tenant）
        - v2：POST /nacos/v2/cs/config（参数 namespaceId）
        - v3：POST /v3/console/cs/config（Console API）

        创建新配置或覆盖已有配置（dataId + group + namespace 唯一确定）。
        """
        try:
            nacos_client = await get_nacos_client()
            success = await nacos_client.publish_config(
                data_id=data_id,
                content=content,
                group_name=group_name,
                namespace_id=namespace_id,
                config_type=config_type.value,
                desc=desc,
            )

            if success:
                ns = namespace_id or nacos_client.default_namespace
                lines = [
                    "配置发布成功",
                    "",
                    "| 属性 | 值 |",
                    "|------|-----|",
                    f"| Data ID | {data_id} |",
                    f"| Group | {group_name} |",
                    f"| Namespace | {ns} |",
                    f"| Type | {config_type.value} |",
                ]
                return "\n".join(lines)
            else:
                return "配置发布失败：未知原因"

        except Exception as e:
            return handle_error(e)

    @mcp.tool(
        name="nacos_delete_config",
        annotations=_rw("删除 Nacos 配置", destructive=True, idempotent=True),
    )
    async def nacos_delete_config(
        data_id: Annotated[str, Field(description="配置 ID", min_length=1, max_length=256)],
        group_name: Annotated[
            str, Field(description="配置分组，默认 DEFAULT_GROUP", min_length=1, max_length=128)
        ] = "DEFAULT_GROUP",
        namespace_id: Annotated[Optional[str], Field(description="命名空间 ID，可选")] = None,
    ) -> str:
        """删除 Nacos 配置（按 dataId + group + namespace 唯一删除）。

        对应 Nacos OpenAPI：
        - v1：DELETE /nacos/v1/cs/configs
        - v2：DELETE /nacos/v2/cs/config
        - v3：DELETE /v3/console/cs/config（Console API）
        """
        try:
            nacos_client = await get_nacos_client()
            success = await nacos_client.delete_config(
                data_id=data_id,
                group_name=group_name,
                namespace_id=namespace_id,
            )
            ns = namespace_id or nacos_client.default_namespace
            if success:
                return f"配置删除成功：dataId={data_id}, group={group_name}, namespace={ns}"
            return "配置删除失败：未知原因"
        except Exception as e:
            return handle_error(e)

    @mcp.tool(name="nacos_create_namespace", annotations=_rw("创建命名空间"))
    async def nacos_create_namespace(
        namespace_id: Annotated[
            str,
            Field(
                description=(
                    "命名空间 ID；优先级：工具参数 > "
                    "NACOS_NAMESPACE 环境变量 > 默认 public"
                ),
                min_length=1,
            ),
        ],
        namespace_name: Annotated[str, Field(description="命名空间名称", min_length=1)],
        namespace_desc: Annotated[Optional[str], Field(description="命名空间描述，可选")] = None,
    ) -> str:
        """创建 Nacos 命名空间（指定命名空间 ID 与名称）。

        对应 Nacos OpenAPI：
        - v1：POST /nacos/v1/console/namespaces（参数 customNamespaceId）
        - v2：POST /nacos/v2/console/namespace（参数 namespaceId）
        - v3：POST /v3/console/core/namespace（Console API，参数 customNamespaceId）
        """
        try:
            nacos_client = await get_nacos_client()
            success = await nacos_client.create_namespace(
                namespace_id=namespace_id,
                namespace_name=namespace_name,
                namespace_desc=namespace_desc,
            )
            if success:
                return f"命名空间创建成功：namespaceId={namespace_id}"
            return "命名空间创建失败：未知原因"
        except Exception as e:
            return handle_error(e)

    @mcp.tool(name="nacos_update_namespace", annotations=_rw("编辑命名空间", idempotent=True))
    async def nacos_update_namespace(
        namespace_id: Annotated[
            str,
            Field(
                description=(
                    "命名空间 ID；优先级：工具参数 > "
                    "NACOS_NAMESPACE 环境变量 > 默认 public"
                ),
                min_length=1,
            ),
        ],
        namespace_name: Annotated[str, Field(description="命名空间名称，必填", min_length=1)],
        namespace_desc: Annotated[Optional[str], Field(description="命名空间描述，可选")] = None,
    ) -> str:
        """更新命名空间名称/描述。

        对应 Nacos OpenAPI：
        - v1：POST /nacos/v1/console/namespaces（参数 namespace）
        - v2：PUT /nacos/v2/console/namespace（参数 namespaceId）
        - v3：PUT /v3/console/core/namespace（Console API）
        """
        try:
            nacos_client = await get_nacos_client()
            success = await nacos_client.update_namespace(
                namespace_id=namespace_id,
                namespace_name=namespace_name,
                namespace_desc=namespace_desc,
            )
            if success:
                return f"命名空间更新成功：namespaceId={namespace_id}"
            return "命名空间更新失败：未知原因"
        except Exception as e:
            return handle_error(e)

    @mcp.tool(
        name="nacos_delete_namespace",
        annotations=_rw("删除命名空间", destructive=True, idempotent=True),
    )
    async def nacos_delete_namespace(
        namespace_id: Annotated[
            str,
            Field(
                description=(
                    "命名空间 ID；优先级：工具参数 > "
                    "NACOS_NAMESPACE 环境变量 > 默认 public"
                ),
                min_length=1,
            ),
        ],
    ) -> str:
        """删除指定命名空间（会一并清除其下所有配置）。

        对应 Nacos OpenAPI：
        - v1：DELETE /nacos/v1/console/namespaces（参数 namespaceId）
        - v2：DELETE /nacos/v2/console/namespace（参数 namespaceId）
        - v3：DELETE /v3/console/core/namespace（Console API）
        """
        try:
            nacos_client = await get_nacos_client()
            success = await nacos_client.delete_namespace(namespace_id=namespace_id)
            if success:
                return f"命名空间删除成功：namespaceId={namespace_id}"
            return "命名空间删除失败：未知原因"
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
    raise ValueError(f"不支持的 MCP_TRANSPORT: {raw!r}，仅支持 stdio、sse、streamable-http")


def _run_http(transport: str) -> None:
    """以 HTTP 方式（sse / streamable-http）运行，并按需启用 Token 认证。"""
    import uvicorn

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))

    if transport == "sse":
        app: Any = mcp.sse_app()
        endpoint = "/sse"
    else:
        app = mcp.streamable_http_app()
        endpoint = "/mcp"

    # 健康检查路由：在鉴权中间件包裹之前挂载，保证无论是否开启鉴权都能探活。
    # MCPServer 原生 app 仅暴露 /mcp（或 /sse），不含 /health。
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    async def _health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app.add_route("/health", _health)

    token = os.getenv("MCP_AUTH_TOKEN")
    if token:
        app = TokenAuthMiddleware(app, token)
        logger.info("HTTP 接口认证已启用（需携带 Authorization: Bearer <token>）")
    else:
        logger.warning("MCP_AUTH_TOKEN 未设置，HTTP 接口处于无鉴权状态，生产环境请务必配置该变量")

    log_level = os.getenv("MCP_LOG_LEVEL", "info").lower()
    logger.info(
        "MCP Server 启动：transport=%s, 监听 http://%s:%s%s",
        transport,
        host,
        port,
        endpoint,
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
