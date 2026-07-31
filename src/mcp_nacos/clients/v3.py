"""Nacos 3.x Console API 客户端。

- 路径前缀：/v3/console/；命名空间路径额外带 /core/ 段
- 创建命名空间：customNamespaceId；编辑/删除：namespaceId
- 返回信封：{code, message, data}
- 登录取 accessToken：POST {base_url}/v3/auth/user/login
"""

import os
import time
from typing import Any, Optional, cast

import httpx2 as httpx

from .base import normalize_namespace, resolve_base_url


class NacosClientV3:
    """Nacos 3.x Console API 客户端"""

    def __init__(self) -> None:
        self.username = os.getenv("NACOS_USERNAME")
        self.password = os.getenv("NACOS_PASSWORD")
        self.default_namespace = os.getenv("NACOS_NAMESPACE", "public")
        self._verify = os.getenv("NACOS_INSECURE", "false").lower() != "true"
        self._client: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = None
        self._token_expire_time: Optional[float] = None

    @property
    def base_url(self) -> str:
        return resolve_base_url()

    async def _ensure_token(self) -> Optional[str]:
        """确保有有效的 access token（如果需要认证）"""
        if not self.username or not self.password:
            return None

        if self._access_token and self._token_expire_time:
            if time.time() < self._token_expire_time - 300:
                return self._access_token

        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/v3/auth/user/login",
            data={"username": self.username, "password": self.password},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        self._access_token = data.get("accessToken")
        ttl = int(data.get("tokenTtl", 18000))
        self._token_expire_time = time.time() + ttl
        return self._access_token

    def _get_namespace(self, namespace_id: Optional[str]) -> str:
        """获取命名空间 ID（含 public->"" 归一化）。"""
        return normalize_namespace(namespace_id or self.default_namespace)

    async def _auth_headers(self) -> dict[str, str]:
        """构造鉴权请求头：同时携带 accessToken 与 Authorization: Bearer。

        兼确保 accessToken 已刷新（官方推荐 Authorization: Bearer，
        历史兼容 accessToken 请求头/参数）。
        """
        await self._ensure_token()
        if not self._access_token:
            return {}
        return {
            "accessToken": self._access_token,
            "Authorization": f"Bearer {self._access_token}",
        }

    @staticmethod
    def _unwrap(result: dict[str, Any]) -> Any:
        """校验信封返回 {code, message, data} 并取出 data"""
        if result.get("code") != 0:
            raise Exception(result.get("message", "Unknown error"))
        return result.get("data")

    async def _get_client(self) -> httpx.AsyncClient:
        """获取共享 AsyncClient（惰性创建，复用连接池）。"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(verify=self._verify)
        return self._client

    async def aclose(self) -> None:
        """关闭共享 AsyncClient，释放连接池。"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    # ---------------- 配置：获取 / 发布 / 删除 ----------------
    async def get_config(
        self,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        await self._ensure_token()
        ns = self._get_namespace(namespace_id)

        params: dict[str, str] = {
            "dataId": data_id,
            "groupName": group_name,
            "namespaceId": ns,
        }
        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v3/console/cs/config",
            params=params,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        if result.get("code") != 0:
            raise Exception(result.get("message", "Unknown error"))

        data: dict[str, Any] = result.get("data") or {}
        return data

    async def publish_config(
        self,
        data_id: str,
        content: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
        config_type: str = "yaml",
        desc: Optional[str] = None,
    ) -> bool:
        await self._ensure_token()
        ns = self._get_namespace(namespace_id)

        params: dict[str, str] = {
            "dataId": data_id,
            "groupName": group_name,
            "namespaceId": ns,
            "content": content,
            "type": config_type,
        }
        if desc:
            params["desc"] = desc

        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/v3/console/cs/config",
            params=params,
            headers=headers,
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
        await self._ensure_token()
        ns = self._get_namespace(namespace_id)

        params: dict[str, str] = {
            "dataId": data_id,
            "groupName": group_name,
            "namespaceId": ns,
        }
        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.delete(
            f"{self.base_url}/v3/console/cs/config",
            params=params,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        return bool(self._unwrap(response.json()))

    # ---------------- 配置历史（Console API 2.14 / 2.15 / 2.16）----------------
    async def list_config_history(
        self,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
        page_no: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        await self._ensure_token()
        ns = self._get_namespace(namespace_id)
        params: dict[str, Any] = {
            "pageNo": page_no,
            "pageSize": page_size,
            "dataId": data_id,
            "groupName": group_name,
            "namespaceId": ns,
        }
        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v3/console/cs/history/list",
            params=params,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        data = self._unwrap(response.json())
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
        await self._ensure_token()
        ns = self._get_namespace(namespace_id)
        params: dict[str, Any] = {
            "nid": nid,
            "dataId": data_id,
            "groupName": group_name,
            "namespaceId": ns,
        }
        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v3/console/cs/history",
            params=params,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        data = self._unwrap(response.json())
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
        await self._ensure_token()
        ns = self._get_namespace(namespace_id)
        params: dict[str, Any] = {
            "id": config_id,
            "dataId": data_id,
            "groupName": group_name,
            "namespaceId": ns,
        }
        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v3/console/cs/history/previous",
            params=params,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        data = self._unwrap(response.json())
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")
        return cast(dict[str, Any], data)

    # ---------------- 配置：命名空间下配置列表（Console API 真列表端点）----------------
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
        """查询命名空间下的配置列表（Nacos 3.x Console API 真列表端点）。

        底层 GET /v3/console/cs/config/list（由 ConsoleConfigController 处理），支持
        dataId/groupName/appName/configTags 过滤（search=blur 模糊 / accurate 精确）与
        pageNo/pageSize 分页，服务端返回 Page<ConfigBasicInfo>（totalCount + pageItems）。
        相比旧的 /v3/console/cs/history/configs 简表，能力与 v1/v2 的搜索配置接口对齐。

        归一化返回 {"total": int, "configs": [{"data_id","group_name","namespace_id",
        "app_name","type"}]}，与 v1/v2 客户端结构一致。
        """
        await self._ensure_token()
        ns = self._get_namespace(namespace_id)
        params: dict[str, Any] = {
            "namespaceId": ns,
            "dataId": data_id or "",
            "groupName": group_name or "",
            "appName": app_name or "",
            "configTags": config_tags or "",
            "search": search,
            "pageNo": page_no,
            "pageSize": page_size,
        }
        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v3/console/cs/config/list",
            params=params,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        data = self._unwrap(response.json())
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")
        page_items = data.get("pageItems", []) or []
        total = data.get("totalCount", 0) or 0
        # 归一化为 {total, configs}（v3 字段为 dataId/groupName/namespaceId），与 v1/v2 一致
        configs = [
            {
                "data_id": i.get("dataId"),
                "group_name": i.get("groupName") or i.get("group"),
                "namespace_id": i.get("namespaceId") or i.get("tenant"),
                "app_name": i.get("appName"),
                "type": i.get("type"),
            }
            for i in page_items
        ]
        return {"total": total, "configs": configs}

    # ---------------- 命名空间（Console API 路径含 /core/ 段）----------------
    async def list_namespaces(self) -> list[dict[str, Any]]:
        await self._ensure_token()
        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v3/console/core/namespace/list",
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        return cast(list[dict[str, Any]], self._unwrap(response.json()))

    async def get_namespace(self, namespace_id: str) -> dict[str, Any]:
        await self._ensure_token()
        ns = self._get_namespace(namespace_id)  # 含 public->"" 归一化
        params: dict[str, str] = {"namespaceId": ns}
        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v3/console/core/namespace",
            params=params,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        data = self._unwrap(response.json())
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")
        return cast(dict[str, Any], data)

    async def create_namespace(
        self,
        namespace_id: str,
        namespace_name: str,
        namespace_desc: Optional[str] = None,
    ) -> bool:
        await self._ensure_token()
        # Console API 创建命名空间使用 customNamespaceId（与 v1 一致，而非 v2 的 namespaceId）
        data: dict[str, str] = {
            "customNamespaceId": namespace_id,
            "namespaceName": namespace_name,
            "namespaceDesc": namespace_desc or "",
        }
        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/v3/console/core/namespace",
            data=data,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        return bool(self._unwrap(response.json()))

    async def update_namespace(
        self,
        namespace_id: str,
        namespace_name: str,
        namespace_desc: Optional[str] = None,
    ) -> bool:
        await self._ensure_token()
        data: dict[str, str] = {
            "namespaceId": namespace_id,
            "namespaceName": namespace_name,
        }
        if namespace_desc is not None:
            data["namespaceDesc"] = namespace_desc
        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.put(
            f"{self.base_url}/v3/console/core/namespace",
            data=data,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        return bool(self._unwrap(response.json()))

    async def delete_namespace(self, namespace_id: str) -> bool:
        await self._ensure_token()
        params: dict[str, str] = {"namespaceId": namespace_id}
        headers: dict[str, str] = await self._auth_headers()

        client = await self._get_client()
        response = await client.delete(
            f"{self.base_url}/v3/console/core/namespace",
            params=params,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        return bool(self._unwrap(response.json()))
