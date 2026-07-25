"""Nacos 客户端基础实现"""

import os
import time
from typing import Any, Optional, Protocol

import httpx


class NacosClientProtocol(Protocol):
    """Nacos 客户端协议"""

    default_namespace: str

    async def get_config(
        self,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
    ) -> dict[str, Any]: ...

    async def publish_config(
        self,
        data_id: str,
        content: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
        config_type: str = "yaml",
        desc: Optional[str] = None,
    ) -> bool: ...


class NacosAuthBase:
    """1.x/2.x 共用的鉴权基类"""

    def __init__(self, host: str, port: int, default_namespace: str) -> None:
        self.host = host
        self.port = port
        self.default_namespace = default_namespace
        self.username = os.getenv("NACOS_USERNAME")
        self.password = os.getenv("NACOS_PASSWORD")
        self._access_token: Optional[str] = None
        self._token_expire_time: Optional[float] = None

    @property
    def base_url(self) -> str:
        """基础 URL"""
        return f"http://{self.host}:{self.port}"

    async def _ensure_token(self) -> Optional[str]:
        """确保有有效的 access token（如果需要认证）"""
        if not self.username or not self.password:
            return None

        if self._access_token and self._token_expire_time:
            if time.time() < self._token_expire_time - 300:
                return self._access_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/nacos/v1/auth/login",
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
