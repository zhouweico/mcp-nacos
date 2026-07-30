"""Nacos 客户端基础实现"""

import logging
import os
import time
from typing import Any, Optional, Protocol

import httpx2 as httpx

logger = logging.getLogger(__name__)

NACOS_BASE_URL_ENV = "NACOS_BASE_URL"
"""环境变量名，用于覆盖 Nacos 基础 URL（支持 HTTPS / 反向代理 / 上下文路径）。"""


def _resolve_base_url(default_host: str, default_port: int) -> str:
    """解析基础 URL（scheme://host[:port]，不含路径）。

    若设置了 ``NACOS_BASE_URL``（如 ``https://nacos.example.com`` 或
    ``https://nacos.example.com/nacos``），则优先使用它，以支持 HTTPS、
    反向代理、带上下文路径等互联网部署；否则回退到 ``http://{host}:{port}``。
    """
    override = os.getenv(NACOS_BASE_URL_ENV)
    if override:
        return override.rstrip("/")
    return f"http://{default_host}:{default_port}"


class NacosClientProtocol(Protocol):
    """Nacos 客户端协议"""

    default_namespace: str

    # ---- 配置读取 / 写入 ----
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

    async def delete_config(
        self,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
    ) -> bool: ...

    # ---- 配置历史 ----
    async def list_config_history(
        self,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
        page_no: int = 1,
        page_size: int = 100,
    ) -> Any: ...

    async def get_config_history(
        self,
        nid: int,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
    ) -> Any: ...

    async def get_config_previous(
        self,
        config_id: int,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
    ) -> Any: ...

    # ---- 命名空间 ----
    async def list_namespaces(self) -> Any: ...

    async def get_namespace(self, namespace_id: str) -> Any: ...

    async def create_namespace(
        self,
        namespace_id: str,
        namespace_name: str,
        namespace_desc: Optional[str] = None,
    ) -> bool: ...

    async def update_namespace(
        self,
        namespace_id: str,
        namespace_name: str,
        namespace_desc: Optional[str] = None,
    ) -> bool: ...

    async def delete_namespace(self, namespace_id: str) -> bool: ...


class NacosAuthBase:
    """1.x/2.x 共用的鉴权基类"""

    def __init__(self, host: str, port: int, default_namespace: str) -> None:
        self.host = host
        self.port = port
        self.default_namespace = default_namespace
        self.username = os.getenv("NACOS_USERNAME")
        self.password = os.getenv("NACOS_PASSWORD")
        self._verify = os.getenv("NACOS_INSECURE", "false").lower() != "true"
        self._client: Optional[httpx.AsyncClient] = None
        if not self._verify:
            logger.warning("NACOS_INSECURE=true 已禁用 TLS 证书验证，存在中间人攻击风险，请仅用于开发/测试环境")
        self._access_token: Optional[str] = None
        self._token_expire_time: Optional[float] = None

    @property
    def base_url(self) -> str:
        """基础 URL（支持 NACOS_BASE_URL 覆盖以支持 HTTPS / 反向代理）"""
        return _resolve_base_url(self.host, self.port)

    @staticmethod
    def _unwrap(result: dict[str, Any]) -> Any:
        """校验 2.x 风格信封返回 {code, message, data} 并取出 data"""
        if result.get("code") != 0:
            raise Exception(result.get("message", "Unknown error"))
        return result.get("data")

    async def _ensure_token(self) -> Optional[str]:
        """确保有有效的 access token（如果需要认证）"""
        if not self.username or not self.password:
            return None

        if self._access_token and self._token_expire_time:
            if time.time() < self._token_expire_time - 300:
                return self._access_token

        client = await self._get_client()
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
