"""工厂版本选择测试。"""

import pytest

import mcp_nacos.clients.factory as factory_mod
from mcp_nacos.clients.factory import _normalize_version, get_nacos_client
from mcp_nacos.clients.v1 import NacosClientV1
from mcp_nacos.clients.v2 import NacosClientV2
from mcp_nacos.clients.v3 import NacosClientV3


async def _client(monkeypatch, version):
    if version is None:
        monkeypatch.delenv("NACOS_VERSION", raising=False)
    else:
        monkeypatch.setenv("NACOS_VERSION", version)
    monkeypatch.setattr(factory_mod, "_cached_client", None)
    return await get_nacos_client()


async def test_default_is_v3(monkeypatch):
    client = await _client(monkeypatch, None)
    assert isinstance(client, NacosClientV3)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", NacosClientV1),
        ("1.x", NacosClientV1),
        ("v1", NacosClientV1),
        ("v1.x", NacosClientV1),
        ("2", NacosClientV2),
        ("2.x", NacosClientV2),
        ("v2", NacosClientV2),
        ("v2.x", NacosClientV2),
        ("3", NacosClientV3),
        ("3.x", NacosClientV3),
        ("v3", NacosClientV3),
        ("v3.x", NacosClientV3),
    ],
)
async def test_explicit_versions(monkeypatch, raw, expected):
    client = await _client(monkeypatch, raw)
    assert isinstance(client, expected)


async def test_invalid_version_raises(monkeypatch):
    monkeypatch.setenv("NACOS_VERSION", "9")
    monkeypatch.setattr(factory_mod, "_cached_client", None)
    with pytest.raises(ValueError):
        await get_nacos_client()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", "1"),
        ("v2", "2"),
        ("3.x", "3"),
        ("x", None),
        ("", None),
    ],
)
def test_normalize_version(raw, expected):
    assert _normalize_version(raw) == expected


@pytest.mark.parametrize("version", ["1", "2", "3"])
async def test_base_url_override(monkeypatch, version):
    """NACOS_BASE_URL 应覆盖 host:port 基础 URL"""
    monkeypatch.setenv("NACOS_VERSION", version)
    monkeypatch.setattr(factory_mod, "_cached_client", None)
    client = await get_nacos_client()
    # 未设置覆盖时默认使用 http://
    url = client.api_base_url if hasattr(client, "api_base_url") else client.base_url
    assert url.startswith("http://")
    # 设置 NACOS_BASE_URL 后应被覆盖
    monkeypatch.setenv("NACOS_BASE_URL", "https://nacos.example.com")
    monkeypatch.setattr(factory_mod, "_cached_client", None)
    client2 = await get_nacos_client()
    if hasattr(client2, "api_base_url"):
        assert client2.api_base_url == "https://nacos.example.com"
        assert client2.console_base_url == "https://nacos.example.com"
    else:
        assert client2.base_url == "https://nacos.example.com"
