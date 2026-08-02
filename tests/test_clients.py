"""客户端路由与返回验证（v1 / v2 / v3）。

通过 httpx.MockTransport 拦截 HTTP，断言：
- 每个方法请求的方法与路径正确（含 v3 的 /core/ 段、groupName 参数）
- 命名空间参数键正确（v1 用 tenant / customNamespaceId / namespace，v2 用 namespaceId，
  v3 创建用 customNamespaceId、其余用 namespaceId）
- 返回值类型正确（裸值 vs {code,message,data} 信封）

注：`request.url.params` 是 httpx 的 `QueryParams` 而非 `dict`；
`dict(params)` 取值时所有 value 会被规范化为 `str`（即使原始 query 看起来像数字）。
下方 `p["pageNo"] == "2"` 等断言依赖这一行为——若 httpx 行为变更需重新评估。
"""

import urllib.parse
from typing import Any

import httpx2 as httpx
import pytest

from mcp_nacos.clients.v1 import NacosClientV1
from mcp_nacos.clients.v2 import NacosClientV2
from mcp_nacos.clients.v3 import NacosClientV3

NS = "dev"  # 使用一个非 public 的命名空间，便于观察参数键差异


# ---------------------------------------------------------------------------
# 预期路由表：EXPECTED[version][method] = (method, path, [必含参数键])
# ---------------------------------------------------------------------------
EXPECTED = {
    "v1": {
        "get_config": ("GET", "/v1/cs/configs", ["dataId", "group", "tenant"]),
        "publish_config": (
            "POST",
            "/v1/cs/configs",
            ["dataId", "group", "content", "type", "tenant"],
        ),
        "delete_config": ("DELETE", "/v1/cs/configs", ["dataId", "group", "tenant"]),
        "list_config_history": (
            "GET",
            "/v1/cs/history",
            ["dataId", "group", "tenant", "pageNo", "pageSize"],
        ),
        "get_config_history": ("GET", "/v1/cs/history", ["nid", "dataId", "group", "tenant"]),
        "get_config_previous": (
            "GET",
            "/v1/cs/history/previous",
            ["id", "dataId", "group", "tenant"],
        ),
        "list_namespaces": ("GET", "/v1/console/namespaces", []),
        "get_namespace": ("GET", "/v1/console/namespaces", []),
        "create_namespace": (
            "POST",
            "/v1/console/namespaces",
            ["customNamespaceId", "namespaceName"],
        ),
        "update_namespace": (
            "PUT",
            "/v1/console/namespaces",
            ["namespace", "namespaceShowName"],
        ),
        "delete_namespace": ("DELETE", "/v1/console/namespaces", ["namespaceId"]),
        "list_configs": (
            "GET",
            "/v1/cs/configs",
            ["search", "tenant", "pageNo", "pageSize"],
        ),
    },
    "v2": {
        "get_config": ("GET", "/v2/cs/config", ["dataId", "group", "namespaceId"]),
        "publish_config": (
            "POST",
            "/v2/cs/config",
            ["dataId", "group", "content", "type", "namespaceId"],
        ),
        "delete_config": ("DELETE", "/v2/cs/config", ["dataId", "group", "namespaceId"]),
        "list_config_history": ("GET", "/v2/cs/history/list", []),
        "get_config_history": ("GET", "/v2/cs/history", []),
        "get_config_previous": ("GET", "/v2/cs/history/previous", []),
        "list_configs": ("GET", "/v1/cs/configs", ["search", "tenant", "pageNo", "pageSize"]),
        "list_namespaces": ("GET", "/v2/console/namespace/list", []),
        "get_namespace": ("GET", "/v2/console/namespace", ["namespaceId"]),
        "create_namespace": (
            "POST",
            "/v2/console/namespace",
            ["namespaceId", "namespaceName"],
        ),
        "update_namespace": (
            "PUT",
            "/v2/console/namespace",
            ["namespaceId", "namespaceName"],
        ),
        "delete_namespace": ("DELETE", "/v2/console/namespace", ["namespaceId"]),
    },
    "v3": {
        "get_config": ("GET", "/v3/console/cs/config", ["dataId", "groupName", "namespaceId"]),
        "publish_config": (
            "POST",
            "/v3/console/cs/config",
            ["dataId", "groupName", "content", "type", "namespaceId"],
        ),
        "delete_config": (
            "DELETE",
            "/v3/console/cs/config",
            ["dataId", "groupName", "namespaceId"],
        ),
        "list_config_history": ("GET", "/v3/console/cs/history/list", []),
        "get_config_history": ("GET", "/v3/console/cs/history", []),
        "get_config_previous": ("GET", "/v3/console/cs/history/previous", []),
        "list_configs": (
            "GET",
            "/v3/console/cs/config/list",
            ["namespaceId", "search", "pageNo", "pageSize"],
        ),
        "list_namespaces": ("GET", "/v3/console/core/namespace/list", []),
        "get_namespace": ("GET", "/v3/console/core/namespace", ["namespaceId"]),
        "create_namespace": (
            "POST",
            "/v3/console/core/namespace",
            ["customNamespaceId", "namespaceName"],
        ),
        "update_namespace": ("PUT", "/v3/console/core/namespace", ["namespaceId", "namespaceName"]),
        "delete_namespace": ("DELETE", "/v3/console/core/namespace", ["namespaceId"]),
    },
}

RETURN_TYPE = {
    "get_config": dict,
    "publish_config": bool,
    "delete_config": bool,
    "list_config_history": dict,
    "get_config_history": dict,
    "get_config_previous": dict,
    "list_configs": dict,
    "list_namespaces": list,
    "get_namespace": dict,
    "create_namespace": bool,
    "update_namespace": bool,
    "delete_namespace": bool,
}


# 各版本 Mock 响应（path 为代码拼接后的纯 API 段，与 fixture 预置 NACOS_BASE_URL=http://localhost:8848 对应）。
def _v1_response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method

    def text_body(s):
        return httpx.Response(200, text=s)

    def json_body(d):
        return httpx.Response(200, json=d)

    if path == "/v1/cs/configs":
        if method == "GET":
            if "search" in request.url.params:
                return json_body(
                    {
                        "totalCount": 1,
                        "pageItems": [
                            {
                                "dataId": "app.yaml",
                                "group": "DEFAULT_GROUP",
                                "tenant": NS,
                                "appName": "",
                                "type": "yaml",
                            }
                        ],
                    }
                )
            return text_body("server:\n  port: 8080\n")
        return text_body("true")
    if path.startswith("/v1/cs/history"):
        return json_body({"data": {"pageItems": [], "totalCount": 0}})
    if path == "/v1/console/namespaces":
        if method == "GET":
            return json_body(
                {
                    "data": [
                        {
                            "namespace": "public",
                            "namespaceShowName": "public",
                            "quota": 200,
                            "configCount": 0,
                        },
                        {
                            "namespace": "dev",
                            "namespaceShowName": "Dev",
                            "quota": 200,
                            "configCount": 1,
                        },
                    ]
                }
            )
        return text_body("true")
    return text_body("true")


def _v2_response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method

    def ok(data):
        return httpx.Response(200, json={"code": 0, "message": "", "data": data})

    if path == "/v2/cs/config":
        if method == "GET":
            return ok("server:\n  port: 8080\n")
        return ok(True)
    if path == "/v1/cs/configs":
        # v2 复用 v1 的 /v1/cs/configs 做配置列表查询，返回裸字典 {totalCount, pageItems}
        return httpx.Response(
            200,
            json={
                "totalCount": 1,
                "pageItems": [
                    {
                        "dataId": "app.yaml",
                        "group": "DEFAULT_GROUP",
                        "tenant": NS,
                        "appName": "",
                        "type": "yaml",
                    }
                ],
            },
        )
    if path.startswith("/v2/cs/history"):
        return ok({"pageItems": [], "totalCount": 0})
    if path == "/v2/console/namespace/list":
        return ok([{"namespace": "public", "namespaceShowName": "public"}])
    if path == "/v2/console/namespace":
        if method == "GET":
            return ok({"namespace": "dev", "namespaceShowName": "Dev"})
        return ok(True)
    return ok(True)


def _v3_response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method

    def ok(data):
        return httpx.Response(200, json={"code": 0, "message": "", "data": data})

    if path == "/v3/console/cs/config":
        if method == "GET":
            return ok(
                {
                    "dataId": "app.yaml",
                    "groupName": "DEFAULT_GROUP",
                    "namespaceId": "public",
                    "content": "server:\n  port: 8080\n",
                    "type": "yaml",
                    "md5": "abc123",
                }
            )
        return ok(True)
    if path == "/v3/console/cs/config/list":
        return ok(
            {
                "totalCount": 1,
                "pageNumber": 1,
                "pagesAvailable": 1,
                "pageItems": [
                    {
                        "dataId": "app.yaml",
                        "groupName": "DEFAULT_GROUP",
                        "namespaceId": "public",
                        "appName": "",
                        "type": "yaml",
                    }
                ],
            }
        )
    if path.startswith("/v3/console/cs/history"):
        return ok({"pageItems": [], "totalCount": 0})
    if path == "/v3/console/core/namespace/list":
        return ok([{"namespace": "public", "namespaceShowName": "public"}])
    if path == "/v3/console/core/namespace":
        if method == "GET":
            return ok({"namespace": "dev", "namespaceShowName": "Dev"})
        return ok(True)
    return ok(True)


HANDLERS = {"v1": _v1_response, "v2": _v2_response, "v3": _v3_response}
CLIENTS = {
    "v1": NacosClientV1,
    "v2": NacosClientV2,
    "v3": NacosClientV3,
}


# ---------------------------------------------------------------------------
# 工具：从 request 提取参数键集合
# ---------------------------------------------------------------------------
def _param_keys(request: httpx.Request) -> set[str]:
    # 合并 query 参数与 form body 参数（DELETE 也可能带 body，如 v1 删除命名空间）
    keys = set(request.url.params.keys())
    if request.method in ("POST", "PUT", "DELETE"):
        body = request.content.decode()
        if body:
            keys |= set(urllib.parse.parse_qs(body, keep_blank_values=True).keys())
    return keys


# ---------------------------------------------------------------------------
# 参数 -> 调用参数
# ---------------------------------------------------------------------------
CALL_KWARGS = {
    "get_config": dict(data_id="app.yaml", group_name="DEFAULT_GROUP", namespace_id=NS),
    "publish_config": dict(
        data_id="app.yaml",
        content="x",
        group_name="DEFAULT_GROUP",
        namespace_id=NS,
        config_type="yaml",
    ),
    "delete_config": dict(data_id="app.yaml", group_name="DEFAULT_GROUP", namespace_id=NS),
    "list_config_history": dict(
        data_id="app.yaml", group_name="DEFAULT_GROUP", namespace_id=NS, page_no=1, page_size=10
    ),
    "get_config_history": dict(nid=5, data_id="app.yaml", group_name="DEFAULT_GROUP", namespace_id=NS),
    "get_config_previous": dict(config_id=7, data_id="app.yaml", group_name="DEFAULT_GROUP", namespace_id=NS),
    "list_namespaces": dict(),
    "get_namespace": dict(namespace_id=NS),
    "create_namespace": dict(namespace_id=NS, namespace_name="Dev", namespace_desc="desc"),
    "update_namespace": dict(namespace_id=NS, namespace_name="Dev2", namespace_desc="desc2"),
    "delete_namespace": dict(namespace_id=NS),
    "list_configs": dict(
        namespace_id=NS,
        data_id="app",
        group_name="DEFAULT_GROUP",
        app_name="",
        config_tags="",
        search="blur",
        page_no=1,
        page_size=10,
    ),
}


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
@pytest.mark.parametrize("method", list(EXPECTED["v1"].keys()))
async def test_client_routing(version, method, http_mock):
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["params"] = _param_keys(request)
        return HANDLERS[version](request)

    http_mock(handler)

    client = CLIENTS[version]()
    exp_method, exp_path, exp_keys = EXPECTED[version][method]

    coro = getattr(client, method)
    result = await coro(**CALL_KWARGS[method])

    # 路由断言
    assert captured["method"] == exp_method, f"[{version}.{method}] 方法应为 {exp_method}，实际 {captured['method']}"
    assert captured["path"] == exp_path, f"[{version}.{method}] 路径应为 {exp_path}，实际 {captured['path']}"

    # 参数键断言（仅当预期非空时，避免对无参接口误报）
    missing = [k for k in exp_keys if k not in captured["params"]]
    assert not missing, f"[{version}.{method}] 缺少参数键 {missing}；实际 {sorted(captured['params'])}"

    # 返回值类型断言
    assert isinstance(result, RETURN_TYPE[method]), (
        f"[{version}.{method}] 返回类型应为 {RETURN_TYPE[method].__name__}，实际 {type(result).__name__}"
    )


# ---------------------------------------------------------------------------
# list_configs：v1/v2 均复用 /v1/cs/configs（Nacos 2.x 无 v2 专属列表端点），
# v3 走 /v3/console/cs/config/list。路由已由上面的 parametric 测试覆盖，
# 这里专门断言返回的归一化结构 {total, configs}。
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
async def test_list_configs_shape(version, http_mock):
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return HANDLERS[version](request)

    http_mock(handler)

    client = CLIENTS[version]()
    result = await client.list_configs(namespace_id=NS)

    assert isinstance(result, dict), f"[{version}] 应返回 dict，实际 {type(result)}"
    assert "total" in result and "configs" in result, f"[{version}] 应含 total/configs，实际 {result}"
    assert isinstance(result["configs"], list) and result["configs"], f"[{version}] configs 应为非空列表"
    first = result["configs"][0]
    assert "data_id" in first and "group_name" in first, f"[{version}] 元素应含 data_id/group_name，实际 {first}"
    assert captured["params"].get("search") == "blur", (
        f"[{version}] search=blur 应被默认下发，实际 {captured['params']}"
    )


# ---------------------------------------------------------------------------
# v3 专属：/v3/console/cs/config/list 真列表端点应透传过滤/分页参数（camelCase），
# 且 total 取服务端 totalCount 而非当前页条数。
# ---------------------------------------------------------------------------
async def test_v3_list_configs_forwards_filters(http_mock):
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "",
                "data": {
                    "totalCount": 42,
                    "pageNumber": 1,
                    "pagesAvailable": 5,
                    "pageItems": [
                        {"dataId": "app.yaml", "groupName": "DEFAULT_GROUP", "namespaceId": NS}
                    ],
                },
            },
        )

    http_mock(handler)

    client = NacosClientV3()
    result = await client.list_configs(
        namespace_id=NS,
        data_id="app",
        group_name="DEFAULT_GROUP",
        app_name="demo",
        config_tags="k=v",
        search="accurate",
        page_no=2,
        page_size=20,
    )

    assert captured["path"] == "/v3/console/cs/config/list"
    p = captured["params"]
    assert p["namespaceId"] == NS
    assert p["dataId"] == "app"
    assert p["groupName"] == "DEFAULT_GROUP"
    assert p["appName"] == "demo"
    assert p["configTags"] == "k=v"
    assert p["search"] == "accurate"
    assert p["pageNo"] == "2"
    assert p["pageSize"] == "20"
    # total 取服务端 totalCount（42），而非当前页 1 条
    assert result["total"] == 42
    assert result["configs"][0]["data_id"] == "app.yaml"


# ---------------------------------------------------------------------------
# public 命名空间归一化：public / PUBLIC / None / "" 都应映射为空串 ""，
# 其他自定义 id 原样返回（本地实测：空串是三版本 public 唯一都通的取值）。
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("public", ""),
        ("PUBLIC", ""),
        ("Public", ""),
        (None, ""),
        ("dev", "dev"),
        ("prod", "prod"),
    ],
)
def test_normalize_namespace(raw, expected):
    from mcp_nacos.clients.base import normalize_namespace

    assert normalize_namespace(raw) == expected


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
async def test_public_normalized_on_wire(version, http_mock):
    """传 public 时，实际下发到服务端的 namespace 参数应为空串 ""。"""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        # form body（v2/v3 发布走 body）
        if request.method in ("POST", "PUT", "DELETE") and request.content:
            captured["params"].update(
                {k: v[0] for k, v in urllib.parse.parse_qs(request.content.decode(), keep_blank_values=True).items()}
            )
        return HANDLERS[version](request)

    http_mock(handler)
    client = CLIENTS[version]()
    # get_config 三版本均带 namespace 参数（v1=tenant / v2,v3=namespaceId）
    await client.get_config(data_id="app.yaml", group_name="DEFAULT_GROUP", namespace_id="public")
    key = "tenant" if version == "v1" else "namespaceId"
    val = captured["params"].get(key)
    # 归一化后 namespace 应表示 public：空串下发（v3）或省略该参数（v1/v2 的 `if ns:`），
    # 二者对服务端都等价于 public；关键是绝不能是字面量 "public"。
    assert val in (None, ""), f"[{version}.get_config] public 应归一化为空串/省略，实际 {key}={val!r}"

    captured["params"] = {}
    await client.list_configs(namespace_id="public")
    val = captured["params"].get(key)
    assert val in (None, ""), f"[{version}.list_configs] public 应归一化为空串/省略，实际 {key}={val!r}"

    captured["params"] = {}
    await client.delete_namespace(namespace_id="public")
    val = captured["params"].get(key)
    assert val in (None, ""), f"[{version}.delete_namespace] public 应归一化为空串/省略，实际 {key}={val!r}"
