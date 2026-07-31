# mcp-nacos

Nacos MCP Server —— 让 AI 助手查询与管理 Nacos 配置。

支持 Nacos 1.x / 2.x / 3.x，按 `NACOS_VERSION` 自动适配。

## 特性

- **多协议传输**：`stdio`（默认）、`sse`、`streamable-http`
- **HTTP 接口认证**：Bearer Token 保护，未授权请求返回 `401`
- **MRTR 确认**：删除配置 / 删除命名空间等破坏性操作触发 MCP 2.0 Elicitation 确认
- **MCP Resources**：`nacos://` URI 暴露命名空间等只读元数据
- **Stateless HTTP**：无会话状态，适配 Serverless / 多副本部署
- **灵活部署**：`uvx` 免安装、Docker 公开镜像、或本地构建

## 快速开始

### MCP 客户端（stdio，本地）

Claude Code 示例，写入项目 `.mcp.json` 或全局 `~/.claude.json`：

```json
{
  "mcpServers": {
    "nacos": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mcp-nacos"],
      "env": {
        "NACOS_BASE_URL": "http://localhost:8848",
        "NACOS_USERNAME": "nacos",
        "NACOS_PASSWORD": "your-password",
        "NACOS_NAMESPACE": "dev",
        "NACOS_VERSION": "3",
        "NACOS_READ_ONLY": "false"
      }
    }
  }
}
```

Cursor / OpenCode / Claude Desktop 等客户端格式相同：`command: uvx` + `args: ["mcp-nacos"]` + `NACOS_*` 环境变量。

**`NACOS_BASE_URL` 格式**（唯一地址参数，三版本通用）：
`scheme://host[:port][/context-path]`。端口缺省按协议默认；是否带 `/nacos` 或反向代理前缀由部署决定，API 段（`/v1/cs/configs`、`/v2/cs/config`、`/v3/console/cs/config` 等）按 `NACOS_VERSION` 自动拼接。典型取值：

| 部署形态 | `NACOS_BASE_URL` 示例 |
|---|---|
| 1.x / 2.x 默认 | `http://<host>:8848/nacos` |
| 3.x 默认（无 contextPath） | `http://<host>:8080` |
| 经网关转发到 `/nacos` | 填网关对外完整地址 |

### Docker（公开镜像，免构建）

公开镜像：`ghcr.io/zhouweico/mcp-nacos:latest`。

**方式一：stdio（客户端拉起容器）**

```json
{
  "mcpServers": {
    "nacos": {
      "type": "stdio",
      "command": "docker",
      "args": ["run", "-i", "--rm", "ghcr.io/zhouweico/mcp-nacos:latest"],
      "env": {
        "NACOS_BASE_URL": "http://your-nacos-host:8080",
        "NACOS_USERNAME": "nacos",
        "NACOS_PASSWORD": "your-password",
        "NACOS_NAMESPACE": "dev",
        "NACOS_VERSION": "3"
      }
    }
  }
}
```

> 必须带 `-i`（保持 stdin 管道）。

**方式二：HTTP + 认证（容器独立运行）**

启动容器：

```bash
docker run -d -p 8000:8000 \
  -e MCP_TRANSPORT=streamable-http \
  -e MCP_AUTH_TOKEN=your-strong-token \
  -e NACOS_BASE_URL=http://your-nacos-host:8848 \
  -e NACOS_VERSION=3 \
  ghcr.io/zhouweico/mcp-nacos:latest
```

客户端 `.mcp.json`：

```json
{
  "mcpServers": {
    "nacos": {
      "type": "streamable-http",
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer your-strong-token"
      }
    }
  }
}
```

## 可用工具

| 工具 | Nacos OpenAPI | 类型 | 说明 | 只读模式 |
|------|---------------|------|------|----------|
| `nacos_get_config` | GET `/cs/config` | 读 | 按 dataId + group + namespace 获取配置 | ✅ |
| `nacos_publish_config` | POST `/cs/config` | 写 | 发布 / 更新配置 | ❌ |
| `nacos_delete_config` | DELETE `/cs/config` | 写 | 删除配置（MRTR 确认） | ❌ |
| `nacos_list_config_history` | GET `/cs/history/list` | 读 | 配置历史列表（分页） | ✅ |
| `nacos_get_config_history` | GET `/cs/history` | 读 | 指定 nid 历史详情 | ✅ |
| `nacos_get_config_previous` | GET `/cs/history/previous` | 读 | 配置上一版本 | ✅ |
| `nacos_list_configs` | v1/v2: `GET /nacos/v1/cs/configs?search=blur`；v3: `GET /v3/console/cs/config/list` | 读 | 命名空间下配置列表（dataId + group 等元数据，不含内容），支持过滤与分页。v1/v2 `search=blur` 不自动补通配符，模糊搜需显式 `*关键词*` | ✅ |
| `nacos_list_namespaces` | GET `/console/namespace/list` | 读 | 查询所有命名空间 | ✅ |
| `nacos_get_namespace` | GET `/console/namespace` | 读 | 查询单个命名空间（v1 由列表过滤模拟） | ✅ |
| `nacos_create_namespace` | POST `/console/namespace` | 写 | 创建命名空间 | ❌ |
| `nacos_update_namespace` | PUT `/console/namespace` | 写 | 编辑命名空间 | ❌ |
| `nacos_delete_namespace` | DELETE `/console/namespace` | 写 | 删除命名空间（MRTR 确认） | ❌ |

**版本端点差异**：

| 版本 | 路径前缀 | 备注 |
|---|---|---|
| v1 | `/v1` | 若部署带 contextPath（如 `/nacos`），体现在 `NACOS_BASE_URL` |
| v2 | `/v2` | 同上 |
| v3 | `/v3/console` | 命名空间路径带 `/core/` 段；accessToken 鉴权 |

v3 创建命名空间字段为 `customNamespaceId`（同 v1），编辑/删除用 `namespaceId`。

**只读模式**：写工具在 `NACOS_READ_ONLY=true` 时注册期排除，Agent 看不到也调不到。

**MRTR 降级**：stdios 等不支持 Elicitation 的客户端，破坏性操作直接执行。

### Nacos 概念

配置唯一键三元组：**namespace → group → dataId**。

- **namespace**：隔离多环境 / 多租户（dev / test / prod）。未指定时用 `NACOS_NAMESPACE`，默认 `public`。
- **group**：同命名空间下的逻辑分组，默认 `DEFAULT_GROUP`。
- **dataId**：配置项唯一标识（通常对应文件名）。
- **type**：`yaml` / `json` / `properties` / `text` / `xml` / `toml` 等，发布时通过 `config_type` 指定。

> 版本字段差异：1.x 用 `tenant` 作命名空间 ID，2.x/3.x 为 `namespaceId`，3.x 创建命名空间又回到 `customNamespaceId`。本 Server 已按版本适配，调用方统一传 `namespace_id` 即可。

## 配置

### 环境变量

**MCP 传输与认证**

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MCP_TRANSPORT` | 传输协议：`stdio` / `sse` / `streamable-http` | `stdio` |
| `MCP_HOST` | HTTP 监听地址（stdio 忽略） | `0.0.0.0` |
| `MCP_PORT` | HTTP 监听端口（stdio 忽略） | `8000` |
| `MCP_AUTH_TOKEN` | 非空时启用 Bearer Token 认证 | -（不鉴权） |
| `MCP_STATELESS_HTTP` | 启用无状态 HTTP（适配 Serverless） | `false` |
| `MCP_LOG_LEVEL` | 日志级别：`debug` / `info` / `warning` / `error` | `info` |

**Nacos 连接**

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `NACOS_BASE_URL` | **必填**。唯一地址参数，格式 `scheme://host[:port][/context-path]`；API 段按版本自动拼接 | - |
| `NACOS_USERNAME` | 用户名 | - |
| `NACOS_PASSWORD` | 密码 | - |
| `NACOS_NAMESPACE` | 默认命名空间 ID | `public` |
| `NACOS_VERSION` | Nacos 版本：`1` / `2` / `3` | `3` |
| `NACOS_READ_ONLY` | 只读模式（禁用写工具） | `false` |
| `NACOS_INSECURE` | 跳过 TLS 证书验证（自签名 / 内部 CA 场景） | `false` |

### 只读模式

```json
{ "env": { "NACOS_READ_ONLY": "true" } }
```

### TLS 证书验证

默认验证 TLS 证书（行为与 httpx 一致）。自签名或内部 CA 环境：

```json
{ "env": { "NACOS_INSECURE": "true" } }
```

> 禁用证书验证不安全，生产环境应使用受信任 CA 签发的有效证书。

## 多协议传输

| 协议 | 端点 | 适用 |
|---|---|---|
| `stdio`（默认） | - | 本地客户端集成（Claude Code、Cursor 等） |
| `sse` | `http://<host>:<port>/sse` | SSE 传输 |
| `streamable-http` | `http://<host>:<port>/mcp` | 远程部署 / 多客户端共享 |

启动示例：

```bash
MCP_TRANSPORT=streamable-http \
MCP_HOST=0.0.0.0 MCP_PORT=8000 \
MCP_AUTH_TOKEN=your-strong-token \
mcp-nacos
```

## 接口认证

`MCP_AUTH_TOKEN` 非空时，HTTP 请求需携带：

```
Authorization: Bearer <MCP_AUTH_TOKEN>
```

兼容 `X-Auth-Token` / `X-MCP-Token` 请求头。`GET /health` 免鉴权（容器探活）。

> `stdio` 不经过网络，不做 Token 认证。未设 `MCP_AUTH_TOKEN` 时 HTTP 接口不鉴权，生产环境务必配置。

## MCP Resources

| URI | 说明 |
|---|---|
| `nacos://namespaces` | 列出所有命名空间 |

## Stateless HTTP 模式

`MCP_STATELESS_HTTP=true`：每次请求独立处理，不保留会话状态。适配 Serverless（AWS Lambda、阿里云函数计算）或多副本部署。

```bash
MCP_TRANSPORT=streamable-http \
MCP_STATELESS_HTTP=true \
MCP_HOST=0.0.0.0 MCP_PORT=8000 \
mcp-nacos
```

> Stateless 模式不支持 SSE 流式响应，每个 HTTP 请求独立完成后返回。

## 容器化部署

### 本地构建（Docker）

```bash
docker build -t mcp-nacos:latest .

docker run -d --name mcp-nacos -p 8000:8000 \
  -e MCP_TRANSPORT=streamable-http \
  -e MCP_AUTH_TOKEN=your-strong-token \
  -e NACOS_BASE_URL=http://your-nacos-host:8080 \
  -e NACOS_USERNAME=nacos \
  -e NACOS_PASSWORD=your-password \
  -e NACOS_NAMESPACE=public \
  -e NACOS_VERSION=3 \
  mcp-nacos:latest
```

### Docker Compose

```bash
cp .env.example .env   # 按需修改
docker compose up -d
```

`docker-compose.yml` 已内置：基于 Dockerfile 构建（标记为 `mcp-nacos:latest`）、`/health` 健康检查、非 root 用户运行。

> 跳过本地构建、直接拉取公开镜像：删除 `build:` 段，只保留 `image: ghcr.io/zhouweico/mcp-nacos:latest`。

## 使用示例

下面示例均为自然语言提示，AI 助手会自动映射到对应 MCP 工具。三元组默认值：namespace=`NACOS_NAMESPACE`、group=`DEFAULT_GROUP`、type=`yaml`。

### 配置查询

```
帮我获取 Nacos 中 dataId 为 "application.yaml" 的配置
```

```
查看 nacos 里 user-service.yml 的配置内容，namespace 是 dev
```

```
列出 dev 命名空间下所有的配置项（只看 dataId 和 group）
```

```
模糊搜索 dataId 包含 "redis" 的配置
```

```
查看 prod 命名空间里 application 的历史版本，第 1 页
```

```
看一下 nid=128 那次历史发布的详细内容
```

```
回滚准备：取 application.yaml 上一版本的内容给我看下
```

### 配置发布与删除

```
把下面这段配置发布到 Nacos，dataId 是 "redis.yaml"：
server:
  port: 6379
```

```
把这段 JSON 配置发布成 order-config.json，类型 json，namespace 用 prod
{"timeout": 3000}
```

```
更新 user-service 的配置，把数据库端口改成 3307
```

```
删除 dev 命名空间下 group=DEFAULT_GROUP、dataId=legacy.properties 的配置
```

> 删除属破坏性操作，支持 MRTR 的客户端会弹出 Elicitation 二次确认；stdio 等不支持的客户端直接执行。

### 命名空间管理

```
列出 Nacos 里所有的命名空间
```

```
查看 dev 命名空间的详情
```

```
新建一个命名空间，id 为 order-prod，名称 "订单生产环境"
```

```
把 dev 命名空间改名为 "开发环境"
```

```
删除命名空间 order-prod
```

### 批量与组合操作

```
把 dev 命名空间下所有配置项的 dataId 和 group 列出来，挑出 redis 相关的给我看内容
```

```
对比 application.yaml 最近两次历史版本的内容差异
```

```
把 test 命名空间的 user-service.yaml 配置同步发布到 prod 命名空间
```

### 只读模式（`NACOS_READ_ONLY=true`）

写工具（发布 / 删除 / 命名空间增删改）在只读模式下不注册，AI 只能执行查询类操作：

```
只读模式下：帮我删除 dataId=legacy.properties 的配置
```

AI 会回复该操作不可用，引导用户关闭只读模式或手动处理。

## License

MIT
