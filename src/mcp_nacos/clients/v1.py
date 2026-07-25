"""Nacos 1.x OpenAPI 客户端"""

from typing import Any, Optional

import httpx

from .base import NacosAuthBase


class NacosClientV1(NacosAuthBase):
    """Nacos 1.x OpenAPI 客户端"""

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
