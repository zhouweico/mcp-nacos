"""Nacos 客户端基础实现"""

import logging
import os
import time
from typing import Any, Optional, Protocol

import httpx2 as httpx

logger = logging.getLogger(__name__)


def resolve_base_url() -> str:
    """读取 `NACOS_BASE_URL`（唯一地址来源），未设置抛出 RuntimeError。

    格式 `scheme://host[:port][/context-path]`。上下文路径（如 ``/nacos``）由部署决定，
    本函数不拼接；各版本客户端仅在其后追加版本 API 段。
    """
    value = os.getenv("NACOS_BASE_URL")
    if not value:
        raise RuntimeError(
            "环境变量 NACOS_BASE_URL 未设置。"
            "格式 scheme://host[:port][/context-path]，"
            "1.x/2.x 默认部署带 /nacos，3.x 默认无；经反向代理时把代理前缀加在地址里。"
        )
    return value.rstrip("/")


# public 命名空间：2.x 以空串表示、3.x 以 "public" 字面量表示；
# 空串在三版本、所有操作中均通过，统一归一化为空串。
_PUBLIC_ALIASES = {"public", "PUBLIC", "Public"}


def normalize_namespace(namespace_id: Optional[str]) -> str:
    """将 public 别名 / None 归一为空串 ""，其余原样返回。"""
    if namespace_id is None:
        return ""
    return "" if namespace_id in _PUBLIC_ALIASES else namespace_id


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
    ) -> dict[str, Any]: ...

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

    # ---- 生命周期 ----
    async def aclose(self) -> None: ...


class NacosAuthBase:
    """1.x/2.x 共用的鉴权与 HTTP 基类"""

    def __init__(self, default_namespace: Optional[str] = None) -> None:
        self.default_namespace = default_namespace if default_namespace is not None else os.getenv(
            "NACOS_NAMESPACE", "public"
        )
        self.username = os.getenv("NACOS_USERNAME")
        self.password = os.getenv("NACOS_PASSWORD")
        self._verify = os.getenv("NACOS_INSECURE", "false").lower() != "true"
        self._client: Optional[httpx.AsyncClient] = None
        if not self._verify:
            logger.warning("NACOS_INSECURE=true 已禁用 TLS 证书验证，请仅用于开发/测试")
        self._access_token: Optional[str] = None
        self._token_expire_time: Optional[float] = None

    @property
    def base_url(self) -> str:
        return resolve_base_url()

    @staticmethod
    def _unwrap(result: dict[str, Any]) -> Any:
        """2.x 信封 {code, message, data}，取出 data"""
        if result.get("code") != 0:
            raise Exception(result.get("message", "Unknown error"))
        return result.get("data")

    async def _ensure_token(self) -> Optional[str]:
        """惰性获取并缓存 access token（tokenTtl 前 5min 刷新）。"""
        if not self.username or not self.password:
            return None
        if self._access_token and self._token_expire_time and time.time() < self._token_expire_time - 300:
            return self._access_token
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/v1/auth/login",
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
        return normalize_namespace(namespace_id or self.default_namespace)

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
