# Changelog

## 0.5.2 (2026-08-02)

### 新增

- **GitHub Actions 工作流**：`ci.yml`（push/PR 到 main 跑 ruff/mypy/pytest 多版本测试、构建 dist、Docker stdio 冒烟）与 `release.yml`（打 v* tag 时校验版本号/CHANGELOG、推多架构 GHCR 镜像、PyPI OIDC 可信发布、GitHub Release）。PyPI 发布改用 Trusted Publisher（OIDC），无需长期令牌。

### 修复

- 补 `NacosClientProtocol.aclose` 协议方法声明，对齐 apisix 范式，修复 mypy strict 报协议缺 aclose。
- 拆分 `server.py` / `test_clients.py` 中超 120 列长字符串字面量（ruff E501 存量问题）。

## 0.5.1 (2026-07-31)

### 修复

- 写操作 namespace 归一化：`update_namespace` / `delete_namespace`（v1/v2/v3）改走 `_get_namespace`，与 `get_namespace` 一致；传 `"public"` 在 v1/v2 不再因服务端 public id 为空串而失败。
- `list_configs` 参数守卫：v1/v2 改为 `if ns: params["tenant"] = ns`，与同文件 `get_config` 风格一致。
- 死代码清理：移除 `UnsupportedVersionError`（无任何 raise 点）及 `handle_error` 中对应特判。

### 文档

- README 标注 `NACOS_BASE_URL` 在 docker compose 启动时为必填。
- 工具 docstring 移除冗余的「只读」「读写」后缀（已通过 MCP `readOnlyHint` 暴露）。

## 0.5.0 (2026-07-31)

### 新增

- **`nacos_list_configs` 工具**：查询命名空间下配置列表，返回 `{total, configs[]}`。v1/v2 走 `GET /v1/cs/configs?search=blur`，v3 走 `GET /v3/console/cs/config/list`，均支持过滤与分页。

### 变更

- **地址参数收敛为 `NACOS_BASE_URL`**：移除 `NACOS_HOST` / `NACOS_PORT` / `NACOS_API_PORT` / `NACOS_CONSOLE_PORT`，未设置时直接抛 `RuntimeError`。
- **路径前缀调整**：客户端不再写死 `/nacos` contextPath，由 `NACOS_BASE_URL` 统一承载；v3 合并 `api_base_url` / `console_base_url` 为单一 `base_url`。
- **public 命名空间归一化**：新增 `normalize_namespace`，`public` / `None` 等统一映射为空串。
- **`NacosAuthBase` 签名简化**：移除 `host` / `port` 入参。

### 文档

- README 新增「使用示例」章节。
- 3.x 默认端口由 `8848` 修正为 `8080`。
- `.env.example` / `docker-compose.yml` 清理废弃环境变量，`NACOS_BASE_URL` 标注为必填。

## 0.4.0 (2026-07-30)

### 新增

- **MCP 2.0 P2 改造**：完整迁移到 MCP SDK v2（`MCPServer`、`ToolAnnotations`、`Context`）
- **破坏性操作 MRTR 确认**：`nacos_delete_config`、`nacos_delete_namespace` 等高危操作通过 MCP 2.0 Elicitation 机制弹出确认表单；不支持 Elicitation 的客户端自动降级为直接执行
- **MCP Resources**：以 `nacos://` URI 暴露命名空间列表等只读元数据
- **Stateless HTTP 模式**：支持 `MCP_STATELESS_HTTP=true` 无状态部署
- **TLS 证书验证跳过**：新增 `NACOS_INSECURE` 环境变量，用于自签名证书环境（开发/测试专用）

### 修复

- 确认机制改为 fail-closed（异常时阻断操作）
- 共享 `httpx.AsyncClient` 实例替代每次新建
- 结构化输出基类增加 `model_config = ConfigDict(extra="allow")`
- 修复 `ruff` E501 行长超限问题
- 统一 `handle_error` 注释描述

### 文档

- README 补充 MRTR 确认、Resources、Stateless HTTP、TLS 跳过等章节
- `.env.example` 补充 `NACOS_INSECURE`
