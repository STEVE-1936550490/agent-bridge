# AgentBridge

AgentBridge 是本地 agent gateway，用一个 CLI 管理 Codex / Claude Code 到不同模型供应商的协议转换、启动和观测。

当前主稳定路径：

```text
Codex /v1/responses -> AgentBridge -> OpenAI Chat Completions provider
```

MOMA GLM-5.x 属于 OpenAI Chat Completions 兼容 provider。AgentBridge 会处理 GLM streaming 中的 `reasoning_content` / `content` 分离，并输出 Codex 可用的 Responses stream。

## 命名

| 名称 | 当前用途 |
|------|----------|
| `AgentBridge` | 产品名 |
| `agent-bridge` | 主 CLI |
| `agent_bridge` | Python 主包名 |
| `moma-proxy` | 旧 CLI 兼容入口，仍可用但不推荐新文档使用 |
| `moma_proxy` | 旧 Python 包名兼容 wrapper，迁移期保留 |
| `moma` | 旧快捷命令：运行 Codex 的 `agent_bridge` profile |

新安装和新脚本都应该使用 `agent-bridge` / `agent_bridge`。

## 快速开始

### 1. 安装项目

Conda 推荐：

```bash
conda create -n agent_bridge python=3.11 -y
conda activate agent_bridge
git clone https://github.com/STEVE-1936550490/MoMa_proxy.git
cd MoMa_proxy
pip install -e ".[dev]"
```

Windows PowerShell 如果 `npm` 被执行策略拦截，请用 `npm.cmd`。

旧环境升级时建议先清掉旧包名元数据，再安装新包名：

```bash
pip uninstall -y moma-proxy
pip install -e ".[dev]"
```

### 2. 检查本地工具

```bash
agent-bridge install
```

需要自动安装 Codex CLI：

```bash
agent-bridge install --install-codex-cli
```

Windows 可手动安装：

```powershell
npm.cmd install -g @openai/codex --registry https://registry.npmmirror.com
```

### 3. 配置 provider

推荐 provider 命名格式：`<平台>_<模型简称>`，例如 `moma_glm51`、`moma_glm52`。

交互式配置：

```bash
agent-bridge configure --config config.yaml
```

脚本式配置：

```bash
agent-bridge configure --config config.yaml --no-interactive \
  --provider moma_glm51 \
  --base-url "https://moma.cmecloud.cn/v1" \
  --api-key-env MOMA_API_KEY \
  --model "ZHIPU/GLM-5.1" \
  --provider-api openai_chat \
  --client-protocol codex_responses
```

`api_key_env` 填环境变量名，不是 key 本身：

```yaml
api_key_env: MOMA_API_KEY
```

如果要直接写 key，用：

```yaml
api_key: your-real-api-key
```

`config.yaml` 已被 `.gitignore` 忽略，不会提交到 Git。

### 4. 日常启动

启动代理并进入 Codex：

```bash
agent-bridge
```

等价显式命令：

```bash
agent-bridge start
```

指定 provider：

```bash
agent-bridge run -p moma_glm51 --client codex
```

透传 Codex 参数：

```bash
agent-bridge run -p moma_glm51 --client codex exec "只输出 OK"
```

启动 Claude Code：

```bash
agent-bridge run -p moma_glm51 --client claude
```

只启动代理用于调试：

```bash
agent-bridge serve --config config.yaml -p moma_glm51
```

健康检查：

```bash
curl http://127.0.0.1:17681/health
```

## 配置示例

```yaml
active_provider: "moma_glm51"
default_model: "ZHIPU/GLM-5.1"

providers:
  moma_glm51:
    base_url: "https://moma.cmecloud.cn/v1"
    api_key_env: "MOMA_API_KEY"
    model: "ZHIPU/GLM-5.1"
    provider_api: "openai_chat"
    client_protocol: "codex_responses"

server:
  host: "0.0.0.0"
  port: 17681

logging:
  level: "INFO"
```

同一平台多个模型就配置多个 provider profile：

```yaml
providers:
  moma_glm51:
    base_url: "https://moma.cmecloud.cn/v1"
    api_key_env: "MOMA_API_KEY"
    model: "ZHIPU/GLM-5.1"
    provider_api: "openai_chat"
    client_protocol: "codex_responses"

  moma_glm52:
    base_url: "https://moma.cmecloud.cn/v1"
    api_key_env: "MOMA_API_KEY"
    model: "ZHIPU/GLM-5.2"
    provider_api: "openai_chat"
    client_protocol: "codex_responses"
```

启动时选择：

```bash
agent-bridge run -p moma_glm52
```

## 协议兼容矩阵

这里的“客户端”指本地 agent CLI，“上游 API 协议”指模型供应商实际暴露的接口协议。

| 客户端 | 上游 API 协议 | 状态 | 说明 |
|--------|---------------|------|------|
| Codex | OpenAI Chat Completions | 已实现，主稳定路径 | Codex 发 `/v1/responses`，AgentBridge 转为上游 `/v1/chat/completions`。 |
| Claude Code | OpenAI Chat Completions | 基础实现，可测试 | Claude Code 发 Anthropic Messages，AgentBridge 转为上游 `/v1/chat/completions`；已覆盖基础 text、tool_use、tool_result。 |
| Codex | OpenAI Responses | 默认兼容，未做代理转换 | 如果上游完整支持 OpenAI Responses，Codex 通常可直接连接；AgentBridge 暂未实现 `codex_responses -> openai_responses`。 |
| Claude Code | Anthropic Messages | 默认兼容，未做代理转换 | 如果上游完整支持 Anthropic Messages，Claude Code 通常可直接连接；AgentBridge 暂未实现 `anthropic -> anthropic_messages`。 |
| Codex | Anthropic Messages | 暂未实现 | 需要 `codex_responses -> anthropic_messages`。 |
| Claude Code | OpenAI Responses | 暂未实现 | 需要 `anthropic -> openai_responses`。 |

当前真正由 AgentBridge 实现的核心转换：

```text
codex_responses -> openai_chat
anthropic -> openai_chat
```

## 端点

| 端点 | 说明 |
|------|------|
| `/v1/responses` | Codex Responses 兼容入口 |
| `/v1/messages` | Claude Code / Anthropic Messages 兼容入口 |
| `/v1/chat/completions` | OpenAI Chat Completions 兼容入口 |
| `/v1/completions` | Legacy completions，自动转换到 chat |
| `/v1/models` | 当前默认模型 |
| `/health` | 健康检查 |
| `/logs` | 最近结构化请求日志 |
| `/dashboard` | 本地日志看板 |

## 观测

查看最近请求日志：

```bash
curl http://127.0.0.1:17681/logs
curl http://127.0.0.1:17681/logs?limit=20
```

打开 dashboard：

```text
http://127.0.0.1:17681/dashboard
```

日志字段包括 request id、provider、model、endpoint、latency、status、stream state、error、token usage 来源。

## 常见问题

### PowerShell 禁止运行 npm/codex.ps1

用 `.cmd`：

```powershell
npm.cmd --version
codex.cmd --version
```

或放开当前用户策略：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### Codex 找不到模型 metadata

Codex 可能输出：

```text
Model metadata for `ZHIPU/GLM-5.1` not found. Defaulting to fallback metadata.
```

这是 Codex 本地没有该非 OpenAI 官方模型的 metadata，不代表 AgentBridge、URL 或 API key 配置错误。只要请求能正常返回内容，通常可以忽略。

### 上游 401: No Bearer Authentication information found

说明 AgentBridge 没读到 provider key。检查：

```bash
python -c "from agent_bridge.config import Config; c=Config.from_file('config.yaml'); p=c.get_provider(); print(c.active_provider, len(p.api_key or ''), p.base_url, p.model)"
```

key 长度为 0 时，检查 `api_key` / `api_key_env`：

```yaml
api_key: your-real-key
```

或：

```yaml
api_key_env: MOMA_API_KEY
```

并确保环境变量存在。

### 端口被旧代理占用

Windows：

```powershell
netstat -ano | findstr :17681
taskkill /PID <pid> /F
```

Linux：

```bash
lsof -i :17681
kill <pid>
```

## 开发

```bash
pytest tests -v
black src tests
isort src tests
mypy src
```

主包名是 `agent_bridge`。`moma_proxy` 仅作为迁移期兼容 wrapper 保留。
