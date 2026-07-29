"""Nacos 1.x OpenAPI 客户端

对接 Nacos 1.x Open API（https://nacos.io/docs/v1/open-api/）。
路径前缀 /nacos/v1，运行在 API 端口（默认 8848）。

版本参数约定（与 2.x/3.x 不同）：
- 命名空间用 tenant 字段（不是 namespaceId）
- 创建命名空间用 customNamespaceId（不是 namespaceId）
- 编辑命名空间用 namespace（不是 namespaceId）
- 返回为裸值/字符串，无 {code,message,data} 信封（发布返回 "true" 表示成功）

覆盖接口：配置 get/publish/delete、配置历史 list/detail/previous、
命名空间 list/get(模拟)/create/update/delete。
"""

from typing import Any, Optional

import httpx

from .base import NacosAuthBase


class NacosClientV1(NacosAuthBase):
    """Nacos 1.x OpenAPI 客户端

    对接 Nacos 1.x Open API（https://nacos.io/docs/v1/open-api/）。
    路径前缀 /nacos/v1，运行在 API 端口（默认 8848）。

    版本参数约定（与 2.x/3.x 不同）：
    - 命名空间用 tenant 字段（不是 namespaceId）
    - 创建命名空间用 customNamespaceId（不是 namespaceId）
    - 编辑命名空间用 namespace（不是 namespaceId）
    - 返回为裸值/字符串，无 {code,message,data} 信封（发布返回 "true" 表示成功）

    覆盖接口：配置 get/publish/delete、配置历史 list/detail/previous、
    命名空间 list/get(模拟)/create/update/delete。
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
            params["tenant"] = ns
        if token:
            params["accessToken"] = token

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/nacos/v1/cs/configs",
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            content = response.text

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
            data["tenant"] = ns
        if desc:
            data["desc"] = desc

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/nacos/v1/cs/configs",
                params=params,
                data=data,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.text.strip().lower()

        return result == "true"

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
            params["tenant"] = ns
        if token:
            params["accessToken"] = token

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/nacos/v1/cs/configs",
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.text.strip().lower()

        return result == "true"

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
            "search": "accurate",
            "dataId": data_id,
            "group": group_name,
            "pageNo": page_no,
            "pageSize": page_size,
        }
        if ns:
            params["tenant"] = ns
        if token:
            params["accessToken"] = token

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/nacos/v1/cs/history",
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

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
            params["tenant"] = ns
        if token:
            params["accessToken"] = token

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/nacos/v1/cs/history",
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

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
            params["tenant"] = ns
        if token:
            params["accessToken"] = token

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/nacos/v1/cs/history/previous",
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    # ---------------- 命名空间 ----------------
    async def list_namespaces(self) -> list[dict[str, Any]]:
        token = await self._ensure_token()
        params: dict[str, str] = {}
        if token:
            params["accessToken"] = token

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/nacos/v1/console/namespaces",
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
        return data.get("data", [])

    async def get_namespace(self, namespace_id: str) -> dict[str, Any]:
        # 1.x 没有"查询单个命名空间"接口，用列表过滤模拟
        items = await self.list_namespaces()
        for item in items:
            if item.get("namespace") == namespace_id:
                return item
        raise Exception(f"命名空间不存在: {namespace_id}")

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
            "customNamespaceId": namespace_id,
            "namespaceName": namespace_name,
        }
        if namespace_desc:
            data["namespaceDesc"] = namespace_desc

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/nacos/v1/console/namespaces",
                params=params,
                data=data,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.text.strip().lower()

        return result == "true"

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

        # 1.x 编辑接口参数：namespace(命名空间ID) / namespaceShowName / namespaceDesc(必填)
        data: dict[str, str] = {
            "namespace": namespace_id,
            "namespaceShowName": namespace_name,
            "namespaceDesc": namespace_desc or "",
        }

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.base_url}/nacos/v1/console/namespaces",
                params=params,
                data=data,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.text.strip().lower()

        return result == "true"

    async def delete_namespace(self, namespace_id: str) -> bool:
        token = await self._ensure_token()
        params: dict[str, str] = {"namespaceId": namespace_id}
        if token:
            params["accessToken"] = token

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/nacos/v1/console/namespaces",
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.text.strip().lower()

        return result == "true"
