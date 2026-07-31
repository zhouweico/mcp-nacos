"""Nacos 2.x OpenAPI 客户端

对接 Nacos 2.x Open API（https://nacos.io/docs/v2/guide/user/open-api/）。
路径前缀 /nacos/v2，运行在 API 端口（默认 8848）。

版本参数约定（相对 1.x 的破坏性变更）：
- 命名空间统一收敛为 namespaceId（1.x 用 tenant / customNamespaceId / namespace）
- 返回统一为 {code,message,data} 信封，真实数据在 data 中
- 配置历史接口位于 /nacos/v2/cs/history/*

覆盖接口：配置 get/publish/delete、配置历史 list/detail/previous、
命名空间 list/get/create/update/delete。
"""

from typing import Any, Optional, cast

from .base import NacosAuthBase


class NacosClientV2(NacosAuthBase):
    """Nacos 2.x OpenAPI 客户端

    对接 Nacos 2.x Open API（https://nacos.io/docs/v2/guide/user/open-api/）。
    路径前缀 /nacos/v2，运行在 API 端口（默认 8848）。

    版本参数约定（相对 1.x 的破坏性变更）：
    - 命名空间统一收敛为 namespaceId（1.x 用 tenant / customNamespaceId / namespace）
    - 返回统一为 {code,message,data} 信封，真实数据在 data 中
    - 配置历史接口位于 /nacos/v2/cs/history/*

    覆盖接口：配置 get/publish/delete、配置历史 list/detail/previous、
    命名空间 list/get/create/update/delete。
    """

    # ---------------- 配置：获取 / 发布 / 删除 ----------------
    async def get_config(
        self,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        token = await self._ensure_token()
        ns = self._get_namespace(namespace_id)

        params: dict[str, str] = {"dataId": data_id, "group": group_name}
        if ns:
            params["namespaceId"] = ns
        if token:
            params["accessToken"] = token

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v2/cs/config",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        if result.get("code") != 0:
            raise Exception(result.get("message", "Unknown error"))

        content = result.get("data", "")
        return {
            "dataId": data_id,
            "groupName": group_name,
            "namespaceId": ns,
            "content": content,
            "type": None,
            "md5": None,
        }

    async def publish_config(
        self,
        data_id: str,
        content: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
        config_type: str = "yaml",
        desc: Optional[str] = None,
    ) -> bool:
        token = await self._ensure_token()
        ns = self._get_namespace(namespace_id)

        params: dict[str, str] = {}
        if token:
            params["accessToken"] = token

        data: dict[str, str] = {
            "dataId": data_id,
            "group": group_name,
            "content": content,
            "type": config_type,
        }
        if ns:
            data["namespaceId"] = ns
        if desc:
            data["desc"] = desc

        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/v2/cs/config",
            params=params,
            data=data,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        if result.get("code") != 0:
            raise Exception(result.get("message", "Unknown error"))

        return bool(result.get("data", False))

    async def delete_config(
        self,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
    ) -> bool:
        token = await self._ensure_token()
        ns = self._get_namespace(namespace_id)

        params: dict[str, str] = {"dataId": data_id, "group": group_name}
        if ns:
            params["namespaceId"] = ns
        if token:
            params["accessToken"] = token

        client = await self._get_client()
        response = await client.delete(
            f"{self.base_url}/v2/cs/config",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        return bool(self._unwrap(result))

    # ---------------- 配置历史 ----------------
    async def list_config_history(
        self,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
        page_no: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        token = await self._ensure_token()
        ns = self._get_namespace(namespace_id)

        params: dict[str, Any] = {
            "dataId": data_id,
            "group": group_name,
            "pageNo": page_no,
            "pageSize": page_size,
        }
        if ns:
            params["namespaceId"] = ns
        if token:
            params["accessToken"] = token

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v2/cs/history/list",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        data = self._unwrap(result)
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")
        return cast(dict[str, Any], data)

    async def get_config_history(
        self,
        nid: int,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        token = await self._ensure_token()
        ns = self._get_namespace(namespace_id)

        params: dict[str, Any] = {"nid": nid, "dataId": data_id, "group": group_name}
        if ns:
            params["namespaceId"] = ns
        if token:
            params["accessToken"] = token

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v2/cs/history",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        data = self._unwrap(result)
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")
        return cast(dict[str, Any], data)

    async def get_config_previous(
        self,
        config_id: int,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        token = await self._ensure_token()
        ns = self._get_namespace(namespace_id)

        params: dict[str, Any] = {"id": config_id, "dataId": data_id, "group": group_name}
        if ns:
            params["namespaceId"] = ns
        if token:
            params["accessToken"] = token

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v2/cs/history/previous",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        data = self._unwrap(result)
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")
        return cast(dict[str, Any], data)

    # ---------------- 配置列表 ----------------
    async def list_configs(
        self,
        namespace_id: Optional[str] = None,
        data_id: Optional[str] = None,
        group_name: Optional[str] = None,
        app_name: Optional[str] = None,
        config_tags: Optional[str] = None,
        search: str = "blur",
        page_no: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """命名空间下配置列表。

        Nacos 2.x 无 v2 专属列表端点，复用 v1 的 GET `{base_url}/v1/cs/configs?search=blur...`
        （与 get_config 的 /v2/cs/config 不同路径；带 search 参数返回分页列表，不带返回单条字符串）。
        """
        token = await self._ensure_token()
        ns = self._get_namespace(namespace_id)
        params: dict[str, Any] = {
            "search": search,
            "dataId": data_id or "",
            "group": group_name or "",
            "appName": app_name or "",
            "config_tags": config_tags or "",
            "tenant": ns,
            "pageNo": page_no,
            "pageSize": page_size,
        }
        if token:
            params["accessToken"] = token

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v1/cs/configs",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")
        page_items = data.get("pageItems", []) or []
        total = data.get("totalCount", 0) or 0
        configs = [
            {
                "data_id": i.get("dataId"),
                "group_name": i.get("group") or i.get("groupName"),
                "namespace_id": i.get("tenant") or i.get("namespaceId"),
                "app_name": i.get("appName"),
                "type": i.get("type"),
            }
            for i in page_items
        ]
        return {"total": total, "configs": configs}

    # ---------------- 命名空间 ----------------
    async def list_namespaces(self) -> list[dict[str, Any]]:
        token = await self._ensure_token()
        params: dict[str, str] = {}
        if token:
            params["accessToken"] = token

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v2/console/namespace/list",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        return cast(list[dict[str, Any]], self._unwrap(result))

    async def get_namespace(self, namespace_id: str) -> dict[str, Any]:
        token = await self._ensure_token()
        ns = self._get_namespace(namespace_id)  # 含 public->"" 归一化
        params: dict[str, str] = {"namespaceId": ns}
        if token:
            params["accessToken"] = token

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v2/console/namespace",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        data = self._unwrap(result)
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")
        return cast(dict[str, Any], data)

    async def create_namespace(
        self,
        namespace_id: str,
        namespace_name: str,
        namespace_desc: Optional[str] = None,
    ) -> bool:
        token = await self._ensure_token()
        params: dict[str, str] = {}
        if token:
            params["accessToken"] = token

        data: dict[str, str] = {
            "namespaceId": namespace_id,
            "namespaceName": namespace_name,
        }
        if namespace_desc:
            data["namespaceDesc"] = namespace_desc

        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/v2/console/namespace",
            params=params,
            data=data,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        return bool(self._unwrap(result))

    async def update_namespace(
        self,
        namespace_id: str,
        namespace_name: str,
        namespace_desc: Optional[str] = None,
    ) -> bool:
        token = await self._ensure_token()
        params: dict[str, str] = {}
        if token:
            params["accessToken"] = token

        data: dict[str, str] = {
            "namespaceId": namespace_id,
            "namespaceName": namespace_name,
        }
        if namespace_desc:
            data["namespaceDesc"] = namespace_desc

        client = await self._get_client()
        response = await client.put(
            f"{self.base_url}/v2/console/namespace",
            params=params,
            data=data,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        return bool(self._unwrap(result))

    async def delete_namespace(self, namespace_id: str) -> bool:
        token = await self._ensure_token()
        params: dict[str, str] = {"namespaceId": namespace_id}
        if token:
            params["accessToken"] = token

        client = await self._get_client()
        response = await client.delete(
            f"{self.base_url}/v2/console/namespace",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        return bool(self._unwrap(result))
