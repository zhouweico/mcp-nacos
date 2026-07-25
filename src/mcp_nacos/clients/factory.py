"""Nacos 客户端工厂"""

import os
from typing import Optional

from .base import NacosClientProtocol
from .v1 import NacosClientV1
from .v2 import NacosClientV2
from .v3 import NacosClientV3

_cached_client: Optional[NacosClientProtocol] = None


def _normalize_version(raw_version: Optional[str]) -> Optional[str]:
    if not raw_version:
        return None
    value = raw_version.strip().lower()
    if value in {"1", "1.x", "v1", "v1.x"}:
        return "1"
    if value in {"2", "2.x", "v2", "v2.x"}:
        return "2"
    if value in {"3", "3.x", "v3", "v3.x"}:
        return "3"
    return None


def _get_configured_version() -> Optional[str]:
    raw_version = os.getenv("NACOS_VERSION")
    if not raw_version:
        return None
    normalized = _normalize_version(raw_version)
    if not normalized:
        raise ValueError("NACOS_VERSION 仅支持 1、2、3")
    return normalized


def _get_host() -> str:
    return os.getenv("NACOS_HOST", "localhost")


def _get_default_namespace() -> str:
    return os.getenv("NACOS_NAMESPACE", "public")


def _get_legacy_port() -> int:
    return int(os.getenv("NACOS_PORT", os.getenv("NACOS_API_PORT", "8848")))


def _build_client(version: str) -> NacosClientProtocol:
    host = _get_host()
    default_namespace = _get_default_namespace()

    if version == "1":
        return NacosClientV1(host, _get_legacy_port(), default_namespace)
    if version == "2":
        return NacosClientV2(host, _get_legacy_port(), default_namespace)
    if version == "3":
        return NacosClientV3()

    raise ValueError(f"不支持的 Nacos 版本: {version}")


async def get_nacos_client() -> NacosClientProtocol:
    """获取 Nacos 客户端（默认 v3，支持显式版本配置）"""
    global _cached_client
    if _cached_client:
        return _cached_client

    version = _get_configured_version() or "3"
    _cached_client = _build_client(version)
    return _cached_client
