"""Nacos 3.x Console API 客户端

对接 Nacos 3.x 的「控制台 API（Console API）」
（https://nacos.io/docs/v3.1/manual/admin/console-api/）。
路径前缀 /v3/console/（默认 $nacos.console.contextPath 为空，即不带 /nacos；若部署配置了
nacos.console.contextPath 则需加回前缀），运行在 console 端口（默认 8080）。
鉴权：登录拿到 accessToken 后，请求头同时携带 accessToken 与
Authorization: Bearer（兼容 Nacos 3.x）。

Nacos 3.x 有三类 HTTP API：
- 客户端 API /v3/client/（端口 8848，仅 GET 配置，无发布）
- 运维 API /v3/admin/（端口 8848，GET/POST/DELETE）
- 控制台 API /v3/console/（端口 8080，accessToken，含发布）—— 本项目即此模块

版本参数约定：
- 命名空间路径带 /core/ 段：/v3/console/core/namespace/*
- 创建命名空间用 customNamespaceId（与 1.x 一致，非 2.x 的 namespaceId）
- 编辑/删除用 namespaceId
- 返回统一为 {code,message,data} 信封

配置历史（对应文档 2.14 / 2.15 / 2.16）同样由 Console API 提供：
- 查询配置发布历史      GET /v3/console/cs/history/list
- 查询某次历史变更记录  GET /v3/console/cs/history          (参数 nid)
- 查询上一变更历史      GET /v3/console/cs/history/previous (参数 id)
三者均使用 groupName 参数与 {code,message,data} 信封返回。

覆盖接口：配置 get/publish/delete、配置历史 list(2.14)/detail(2.15)/previous(2.16)、
命名空间 list/get/create/update/delete。
"""

import os
import time
from typing import Any, Optional

import httpx

from .base import _resolve_base_url


class NacosClientV3:
    """Nacos 3.x Console API 客户端"""

    def __init__(self) -> None:
        self.host = os.getenv("NACOS_HOST", "localhost")
        self.api_port = int(os.getenv("NACOS_API_PORT", "8848"))
        self.console_port = int(os.getenv("NACOS_CONSOLE_PORT", "8080"))
        self.username = os.getenv("NACOS_USERNAME")
        self.password = os.getenv("NACOS_PASSWORD")
        self.default_namespace = os.getenv("NACOS_NAMESPACE", "public")

        self._access_token: Optional[str] = None
        self._token_expire_time: Optional[float] = None

    @property
    def api_base_url(self) -> str:
        """API 端口 URL（用于登录，支持 NACOS_BASE_URL 覆盖）"""
        return _resolve_base_url(self.host, self.api_port)

    @property
    def console_base_url(self) -> str:
        """Console 端口 URL（用于配置/命名空间操作，支持 NACOS_BASE_URL 覆盖）"""
        return _resolve_base_url(self.host, self.console_port)

    async def _ensure_token(self) -> Optional[str]:
        """确保有有效的 access token（如果需要认证）"""
        if not self.username or not self.password:
            return None

        if self._access_token and self._token_expire_time:
            if time.time() < self._token_expire_time - 300:
                return self._access_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base_url}/nacos/v3/auth/user/login",
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
        """获取命名空间 ID"""
        return namespace_id or self.default_namespace

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

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.console_base_url}/v3/console/cs/config",
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

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.console_base_url}/v3/console/cs/config",
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

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.console_base_url}/v3/console/cs/config",
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

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.console_base_url}/v3/console/cs/history/list",
                params=params,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return self._unwrap(response.json())

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

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.console_base_url}/v3/console/cs/history",
                params=params,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return self._unwrap(response.json())

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

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.console_base_url}/v3/console/cs/history/previous",
                params=params,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return self._unwrap(response.json())

    # ---------------- 命名空间（Console API 路径含 /core/ 段）----------------
    async def list_namespaces(self) -> list[dict[str, Any]]:
        await self._ensure_token()
        headers: dict[str, str] = await self._auth_headers()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.console_base_url}/v3/console/core/namespace/list",
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return self._unwrap(response.json())

    async def get_namespace(self, namespace_id: str) -> dict[str, Any]:
        await self._ensure_token()
        params: dict[str, str] = {"namespaceId": namespace_id}
        headers: dict[str, str] = await self._auth_headers()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.console_base_url}/v3/console/core/namespace",
                params=params,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return self._unwrap(response.json())

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

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.console_base_url}/v3/console/core/namespace",
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

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.console_base_url}/v3/console/core/namespace",
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

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.console_base_url}/v3/console/core/namespace",
                params=params,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return bool(self._unwrap(response.json()))
