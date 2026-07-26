"""客户端路由与返回验证（v1 / v2 / v3）。

通过 httpx.MockTransport 拦截 HTTP，断言：
- 每个方法请求的方法与路径正确（含 v3 的 /core/ 段、groupName 参数）
- 命名空间参数键正确（v1 用 tenant / customNamespaceId / namespace，v2 用 namespaceId，
  v3 创建用 customNamespaceId、其余用 namespaceId）
- 返回值类型正确（裸值 vs {code,message,data} 信封）
"""

import urllib.parse
from typing import Any

import httpx
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
        "get_config": ("GET", "/nacos/v1/cs/configs", ["dataId", "group", "tenant"]),
        "publish_config": ("POST", "/nacos/v1/cs/configs", ["dataId", "group", "content", "type", "tenant"]),
        "delete_config": ("DELETE", "/nacos/v1/cs/configs", ["dataId", "group", "tenant"]),
        "list_config_history": ("GET", "/nacos/v1/cs/history", ["dataId", "group", "tenant", "pageNo", "pageSize"]),
        "get_config_history": ("GET", "/nacos/v1/cs/history", ["nid", "dataId", "group", "tenant"]),
        "get_config_previous": ("GET", "/nacos/v1/cs/history/previous", ["id", "dataId", "group", "tenant"]),
        "list_namespaces": ("GET", "/nacos/v1/console/namespaces", []),
        "get_namespace": ("GET", "/nacos/v1/console/namespaces", []),
        "create_namespace": ("POST", "/nacos/v1/console/namespaces", ["customNamespaceId", "namespaceName"]),
        "update_namespace": ("PUT", "/nacos/v1/console/namespaces", ["namespace", "namespaceShowName"]),
        "delete_namespace": ("DELETE", "/nacos/v1/console/namespaces", ["namespaceId"]),
    },
    "v2": {
        "get_config": ("GET", "/nacos/v2/cs/config", ["dataId", "group", "namespaceId"]),
        "publish_config": ("POST", "/nacos/v2/cs/config", ["dataId", "group", "content", "type", "namespaceId"]),
        "delete_config": ("DELETE", "/nacos/v2/cs/config", ["dataId", "group", "namespaceId"]),
        "list_config_history": ("GET", "/nacos/v2/cs/history/list", []),
        "get_config_history": ("GET", "/nacos/v2/cs/history", []),
        "get_config_previous": ("GET", "/nacos/v2/cs/history/previous", []),
        "list_namespaces": ("GET", "/nacos/v2/console/namespace/list", []),
        "get_namespace": ("GET", "/nacos/v2/console/namespace", ["namespaceId"]),
        "create_namespace": ("POST", "/nacos/v2/console/namespace", ["namespaceId", "namespaceName"]),
        "update_namespace": ("PUT", "/nacos/v2/console/namespace", ["namespaceId", "namespaceName"]),
        "delete_namespace": ("DELETE", "/nacos/v2/console/namespace", ["namespaceId"]),
    },
    "v3": {
        "get_config": ("GET", "/v3/console/cs/config", ["dataId", "groupName", "namespaceId"]),
        "publish_config": ("POST", "/v3/console/cs/config", ["dataId", "groupName", "content", "type", "namespaceId"]),
        "delete_config": ("DELETE", "/v3/console/cs/config", ["dataId", "groupName", "namespaceId"]),
        "list_config_history": ("GET", "/v3/console/cs/history/list", []),
        "get_config_history": ("GET", "/v3/console/cs/history", []),
        "get_config_previous": ("GET", "/v3/console/cs/history/previous", []),
        "list_namespaces": ("GET", "/v3/console/core/namespace/list", []),
        "get_namespace": ("GET", "/v3/console/core/namespace", ["namespaceId"]),
        "create_namespace": ("POST", "/v3/console/core/namespace", ["customNamespaceId", "namespaceName"]),
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
    "list_namespaces": list,
    "get_namespace": dict,
    "create_namespace": bool,
    "update_namespace": bool,
    "delete_namespace": bool,
}


# ---------------------------------------------------------------------------
# 各版本的 Mock 响应构造
# ---------------------------------------------------------------------------
def _v1_response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method
    text_body = lambda s: httpx.Response(200, text=s)
    json_body = lambda d: httpx.Response(200, json=d)

    if path == "/nacos/v1/cs/configs":
        if method == "GET":
            return text_body("server:\n  port: 8080\n")
        return text_body("true")  # POST / DELETE
    if path.startswith("/nacos/v1/cs/history"):
        return json_body({"data": {"pageItems": [], "totalCount": 0}})
    if path == "/nacos/v1/console/namespaces":
        if method == "GET":
            return json_body({
                "data": [
                    {"namespace": "public", "namespaceShowName": "public", "quota": 200, "configCount": 0},
                    {"namespace": "dev", "namespaceShowName": "Dev", "quota": 200, "configCount": 1},
                ]
            })
        return text_body("true")
    return text_body("true")


def _v2_response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method
    ok = lambda data: httpx.Response(200, json={"code": 0, "message": "", "data": data})

    if path == "/nacos/v2/cs/config":
        if method == "GET":
            return ok("server:\n  port: 8080\n")
        return ok(True)
    if path.startswith("/nacos/v2/cs/history"):
        return ok({"pageItems": [], "totalCount": 0})
    if path == "/nacos/v2/console/namespace/list":
        return ok([{"namespace": "public", "namespaceShowName": "public"}])
    if path == "/nacos/v2/console/namespace":
        if method == "GET":
            return ok({"namespace": "dev", "namespaceShowName": "Dev"})
        return ok(True)
    return ok(True)


def _v3_response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method
    ok = lambda data: httpx.Response(200, json={"code": 0, "message": "", "data": data})

    if path == "/v3/console/cs/config":
        if method == "GET":
            return ok({
                "dataId": "app.yaml", "groupName": "DEFAULT_GROUP", "namespaceId": "public",
                "content": "server:\n  port: 8080\n", "type": "yaml", "md5": "abc123",
            })
        return ok(True)
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
CLIENTS = {"v1": lambda: NacosClientV1("localhost", 8848, "public"),
           "v2": lambda: NacosClientV2("localhost", 8848, "public"),
           "v3": lambda: NacosClientV3()}


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
    "publish_config": dict(data_id="app.yaml", content="x", group_name="DEFAULT_GROUP", namespace_id=NS, config_type="yaml"),
    "delete_config": dict(data_id="app.yaml", group_name="DEFAULT_GROUP", namespace_id=NS),
    "list_config_history": dict(data_id="app.yaml", group_name="DEFAULT_GROUP", namespace_id=NS, page_no=1, page_size=10),
    "get_config_history": dict(nid=5, data_id="app.yaml", group_name="DEFAULT_GROUP", namespace_id=NS),
    "get_config_previous": dict(config_id=7, data_id="app.yaml", group_name="DEFAULT_GROUP", namespace_id=NS),
    "list_namespaces": dict(),
    "get_namespace": dict(namespace_id=NS),
    "create_namespace": dict(namespace_id=NS, namespace_name="Dev", namespace_desc="desc"),
    "update_namespace": dict(namespace_id=NS, namespace_name="Dev2", namespace_desc="desc2"),
    "delete_namespace": dict(namespace_id=NS),
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
