# mcp-nacos

Nacos MCP Server - 让 AI 助手能够查询和管理 Nacos 配置。

支持 Nacos 1.x / 2.x / 3.x 版本，自动适配对应客户端。

## 特性

- **多协议传输**：`stdio`（默认）、`sse`、`streamable-http`，一套代码适配本地与远程场景
- **接口认证**：HTTP 传输支持 Bearer Token 保护，未授权请求返回 `401`
- **Nacos 兼容**：自动适配 v1 / v2 / v3，无需改动配置结构
- **灵活部署**：`uvx` 免安装运行、Docker 公开镜像即拉即用、或本地构建

## 快速开始

### MCP 客户端（stdio，本地）

以 Claude Code 为例，在项目 `.mcp.json` 或全局 `~/.claude.json` 中添加：

```json
{
  "mcpServers": {
    "nacos": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mcp-nacos"],
      "env": {
        "NACOS_HOST": "localhost",
        "NACOS_API_PORT": "8848",
        "NACOS_CONSOLE_PORT": "8080",
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

> Cursor、OpenCode、Claude Desktop 等客户端的配置格式相同，核心均为 `command: uvx` + `args: ["mcp-nacos"]`，按各客户端语法填入 `NACOS_*` 环境变量即可。

### Docker（公开镜像，免构建）

已发布公开镜像 `ghcr.io/zhouweico/mcp-nacos:latest`，无需本地构建。下面以 Claude Code 为例，说明如何用 `docker` 命令运行并配置 mcp-nacos。

**方式一：stdio（由客户端拉起容器，适合本地集成）**

在 Claude Code 的 `.mcp.json` 中直接用 `docker` 作为启动命令，客户端会以 stdio 管道与容器内服务通信：

```json
{
  "mcpServers": {
    "nacos": {
      "type": "stdio",
      "command": "docker",
      "args": ["run", "-i", "--rm", "ghcr.io/zhouweico/mcp-nacos:latest"],
      "env": {
        "NACOS_HOST": "your-nacos-host",
        "NACOS_API_PORT": "8848",
        "NACOS_CONSOLE_PORT": "8080",
        "NACOS_USERNAME": "nacos",
        "NACOS_PASSWORD": "your-password",
        "NACOS_NAMESPACE": "dev",
        "NACOS_VERSION": "3"
      }
    }
  }
}
```

> 必须带 `-i`（保持 stdin 管道），否则容器内的 stdio 服务无法与客户端通信。

**方式二：HTTP + 认证（容器独立运行，客户端远程连接，适合多客户端共享）**

先启动容器：

```bash
docker run -d -p 8000:8000 \
  -e MCP_TRANSPORT=streamable-http \
  -e MCP_AUTH_TOKEN=your-strong-token \
  -e NACOS_HOST=your-nacos-host \
  -e NACOS_VERSION=3 \
  ghcr.io/zhouweico/mcp-nacos:latest
```

再在 Claude Code 的 `.mcp.json` 中通过 HTTP 连接：

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

| 工具 | 对应 Nacos OpenAPI | 类型 | 说明 | 只读模式 |
|------|------|------|------|----------|
| `nacos_get_config` | GET `/cs/config` | 只读 | 按 dataId + group + namespace 获取配置内容 | ✅ 可用 |
| `nacos_publish_config` | POST `/cs/config` | 写 | 发布/更新配置（dataId + group + namespace 唯一确定） | ❌ 禁用 |
| `nacos_delete_config` | DELETE `/cs/config` | 写 | 删除配置 | ❌ 禁用 |
| `nacos_list_config_history` | GET `/cs/history/list`（2.14） | 只读 | 配置历史版本列表（分页） | ✅ 可用 |
| `nacos_get_config_history` | GET `/cs/history`（2.15） | 只读 | 指定历史版本（nid）详情 | ✅ 可用 |
| `nacos_get_config_previous` | GET `/cs/history/previous`（2.16） | 只读 | 配置上一版本信息（id） | ✅ 可用 |
| `nacos_list_namespaces` | GET `/console/namespace/list` | 只读 | 查询所有命名空间 | ✅ 可用 |
| `nacos_get_namespace` | GET `/console/namespace` | 只读 | 查询单个命名空间（v1 由列表过滤模拟） | ✅ 可用 |
| `nacos_create_namespace` | POST `/console/namespace` | 写 | 创建命名空间 | ❌ 禁用 |
| `nacos_update_namespace` | PUT `/console/namespace` | 写 | 编辑命名空间名称/描述 | ❌ 禁用 |
| `nacos_delete_namespace` | DELETE `/console/namespace` | 写 | 删除命名空间 | ❌ 禁用 |

> 版本路径前缀不同，同一工具在 v1 / v2 / v3 下命中的端点不同：
> - v1：`/nacos/v1`（API 端口 8848）
> - v2：`/nacos/v2`（API 端口 8848）
> - v3：`/nacos/v3/console`（Console API，端口 8080，accessToken 鉴权）
>
> 其中 v3 的命名空间路径额外带 `/core/` 段（如 `/v3/console/core/namespace/list`），创建命名空间用 `customNamespaceId`（与 v1 一致），编辑/删除用 `namespaceId`。

> 标注"❌ 禁用"的工具在 `NACOS_READ_ONLY=true` 时**不注册**（注册期排除，非运行期拦截），Agent 既看不到也无法调用；"✅ 可用"的只读工具在只读模式下仍可使用。生产环境开启只读后，Agent 只能查询、绝无意外改配置的风险。

> 历史版本（2.14 / 2.15 / 2.16）与命名空间相关接口覆盖 Nacos 1.x / 2.x / 3.x（除"监听配置"长轮询外）。v3 历史接口已对照官方 Console API 文档核实，路径为 `/v3/console/cs/history/*`。

### Nacos 概念说明

Nacos 配置的组织层级为：**命名空间（namespace）> 分组（group）> 配置（dataId）**，三者共同唯一确定一个配置项：

- **namespace（命名空间）**：用于隔离不同环境或租户（如 dev / test / prod）。不指定时回退 `NACOS_NAMESPACE`，默认 `public`。
- **group（分组）**：同一命名空间下的逻辑分组，默认 `DEFAULT_GROUP`。
- **dataId（配置 ID）**：配置项的唯一标识，通常对应文件名（如 `application.yaml`、`user-service.yml`）。
- **配置格式（type）**：`yaml` / `json` / `properties` / `text` / `xml` / `toml` 等，发布时通过 `config_type` 指定。

> 版本差异提示：1.x 用 `tenant` 表示命名空间 ID，2.x/3.x 收敛为 `namespaceId`；3.x 控制台 API 创建命名空间又回到 `customNamespaceId`（与 1.x 一致）。本 MCP Server 已按版本自动适配这些字段名，调用方只需传 `namespace_id` 即可。

## 配置

## 配置

### 环境变量

**MCP 传输与认证**

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MCP_TRANSPORT` | 传输协议：`stdio` / `sse` / `streamable-http` | `stdio` |
| `MCP_HOST` | HTTP 传输监听地址（stdio 忽略） | `0.0.0.0` |
| `MCP_PORT` | HTTP 传输监听端口（stdio 忽略） | `8000` |
| `MCP_AUTH_TOKEN` | 设置后启用 Bearer Token 认证，保护 HTTP 接口 | -（不鉴权） |
| `MCP_LOG_LEVEL` | 日志级别：`debug`/`info`/`warning`/`error` | `info` |

**Nacos 连接**

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `NACOS_HOST` | Nacos 服务地址 | `localhost` |
| `NACOS_BASE_URL` | **覆盖基础 URL**（如 `https://nacos.example.com` 或 `https://nacos.example.com/nacos`），用于 HTTPS / 反向代理 / 带上下文路径的互联网部署；设置后 `NACOS_HOST` / `NACOS_PORT` / `NACOS_API_PORT` / `NACOS_CONSOLE_PORT` 不再生效 | - |
| `NACOS_PORT` | API 端口（仅 v1/v2 使用，v1/v2 必填） | `8848` |
| `NACOS_API_PORT` | API 端口（用于登录，仅 v3 使用，v3 必填） | `8848` |
| `NACOS_CONSOLE_PORT` | Console 端口（用于配置操作，仅 v3 使用，v3 必填） | `8080` |
| `NACOS_USERNAME` | 用户名（可选） | - |
| `NACOS_PASSWORD` | 密码（可选） | - |
| `NACOS_NAMESPACE` | 默认命名空间 ID（当 `NACOS_VERSION=1` 时表示 Nacos 的命名空间 ID 字段） | `public` |
| `NACOS_VERSION` | Nacos 版本（1/2/3），默认 3 | `3` |
| `NACOS_READ_ONLY` | 只读模式，禁用发布功能（适合生产环境） | `false` |

### 只读模式

设置 `NACOS_READ_ONLY=true` 可禁用发布功能，仅允许查询配置，适合生产环境使用。在客户端配置的环境变量中加入：

```json
{
  "env": {
    "NACOS_READ_ONLY": "true"
  }
}
```

## 多协议传输

通过 `MCP_TRANSPORT` 选择传输协议：

- **`stdio`（默认）**：标准输入输出，适合 Claude Code、Cursor 等本地 AI 客户端集成。
- **`sse`**：Server-Sent Events，HTTP 传输，端点 `http://<host>:<port>/sse`。
- **`streamable-http`**：Streamable HTTP，端点 `http://<host>:<port>/mcp`。

以 `streamable-http` 启动示例：

```bash
MCP_TRANSPORT=streamable-http \
MCP_HOST=0.0.0.0 MCP_PORT=8000 \
MCP_AUTH_TOKEN=your-strong-token \
mcp-nacos
```

## 接口认证

设置 `MCP_AUTH_TOKEN` 后，所有 HTTP 请求必须携带正确 Token，否则返回 `401`：

```
Authorization: Bearer <MCP_AUTH_TOKEN>
```

也兼容 `X-Auth-Token` / `X-MCP-Token` 请求头。健康检查端点 `GET /health` 免鉴权，返回 `{"status":"ok"}`，用于容器探活。

> `stdio` 传输为本地进程通信，不涉及网络，无需也不会进行 Token 认证。未设置 `MCP_AUTH_TOKEN` 时 HTTP 接口不鉴权，生产环境请务必配置。

## 容器化部署

### 本地构建（Docker）

如需本地构建或定制镜像：

```bash
# 构建镜像
docker build -t mcp-nacos:latest .

# 以 streamable-http 运行并启用认证
docker run -d --name mcp-nacos -p 8000:8000 \
  -e MCP_TRANSPORT=streamable-http \
  -e MCP_AUTH_TOKEN=your-strong-token \
  -e NACOS_HOST=your-nacos-host \
  -e NACOS_API_PORT=8848 \
  -e NACOS_CONSOLE_PORT=8080 \
  -e NACOS_USERNAME=nacos \
  -e NACOS_PASSWORD=your-password \
  -e NACOS_NAMESPACE=public \
  -e NACOS_VERSION=3 \
  mcp-nacos:latest
```

> 直接拉取已发布的公开镜像、免本地构建的用法见 [快速开始 → Docker](#docker公开镜像免构建)。

### Docker Compose

复制 `.env.example` 为 `.env` 并按需修改，然后：

```bash
cp .env.example .env
docker compose up -d
```

`docker-compose.yml` 已内置 `build`（基于本地 `Dockerfile` 构建并标记为 `mcp-nacos:latest`）和健康检查（探测 `/health`），以非 root 用户运行，适合本地开发部署。

> 若想直接运行已发布的公开镜像、跳过本地构建，可将 `docker-compose.yml` 中的 `build:` 段删除，仅保留 `image: ghcr.io/zhouweico/mcp-nacos:latest`。

## 使用场景示例

配置好后，你可以这样和 AI 对话：

**查询配置：**

```
帮我获取 Nacos 中 dataId 为 "application.yaml" 的配置
```

```
查看 nacos 里 user-service.yml 的配置内容，namespace 是 dev
```

```
获取 gateway 的配置，分组是 PROD_GROUP
```

```
列出 dev 命名空间下的所有命名空间
```

```
查看 prod 命名空间里 application 这个配置的历史版本，第 1 页
```

```
查一下 application 配置 nid 为 123 的那次历史变更内容
```

**发布配置：**

```
把下面这段配置发布到 Nacos，dataId 是 "redis.yaml"：
server:
  port: 6379
```

```
更新 user-service 的配置，把数据库端口改成 3307
```

```
新建一个命名空间，id 为 order-prod，名称 "订单生产环境"
```

## License

MIT
