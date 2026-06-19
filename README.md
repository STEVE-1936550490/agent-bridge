# AgentBridge

AgentBridge 是本地 agent gateway，用一个 CLI 管理 Codex / Claude Code 到不同模型供应商的协议转换、启动和观测。

当前主稳定路径：

```text
Codex /v1/responses -> AgentBridge -> OpenAI Chat Completions provider
```

GLM-5.x 属于 OpenAI Chat Completions 兼容 provider。AgentBridge 会处理 GLM streaming 中的 `reasoning_content` / `content` 分离，并输出 Codex 可用的 Responses stream。

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
git clone https://github.com/STEVE-1936550490/agent-bridge.git
cd agent-bridge
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
  --api-key-env AGENT_BRIDGE_API_KEY \
  --model "ZHIPU/GLM-5.1" \
  --provider-api openai_chat \
  --client-protocol codex_responses
```

`api_key_env` 填环境变量名，不是 key 本身：

```yaml
api_key_env: API_KEY
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

切换到其他 provider（model 会自动同步到 Codex profile）：

```bash
agent-bridge run -p moma_glm52 --client codex
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
    api_key_env: "AGENT_BRIDGE_API_KEY"
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
    api_key_env: "AGENT_BRIDGE_API_KEY"
    model: "ZHIPU/GLM-5.1"
    provider_api: "openai_chat"
    client_protocol: "codex_responses"

  moma_glm52:
    base_url: "https://moma.cmecloud.cn/v1"
    api_key_env: "AGENT_BRIDGE_API_KEY"
    model: "ZHIPU/GLM-5.2"
    provider_api: "openai_chat"
    client_protocol: "codex_responses"
```

启动时选择：

```bash
agent-bridge run -p moma_glm52
```

## 协议兼容矩阵

这里的"客户端"指本地 agent CLI，"上游 API 协议"指模型供应商实际暴露的接口协议。

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

## 推理强度调节

Codex 和部分客户端通过 `reasoning: {"effort": "minimal"|"low"|"medium"|"high"}`
控制模型回答前的思考程度。不同上游 provider 对这个参数的支持方式不同，AgentBridge
在代理层做转换，让调节在所有 provider 上都能生效。

### 工作方式

在 provider 配置里设置 `reasoning_mode`：

| reasoning_mode | 行为 | 适用 provider |
|----------------|------|---------------|
| `passthrough`（默认） | 直接把 `reasoning_effort` 透传给上游 | OpenAI 官方等标准 provider |
| `thinking` | effort 映射成 `thinking: {"type": "enabled"/"disabled"}` | 智谱 GLM / MOMA（只支持开/关，不支持强度梯度） |
| `none` | 不处理，不向上游发送任何 reasoning 字段 | 明确不需要调节的 provider |

`thinking` 模式的映射规则（探测确认 GLM 上游只支持开/关二态）：

| Codex effort | 映射结果 | 效果 |
|--------------|----------|------|
| `minimal` / `low` | `thinking: {"type": "disabled"}` | 关闭思考，响应快 |
| `medium` / `high` | `thinking: {"type": "enabled"}` | 开启思考，响应慢但更深入 |

### 配置

`config.yaml` 中给 provider 加 `reasoning_mode`：

```yaml
providers:
  moma_glm51:
    base_url: "https://moma.cmecloud.cn/v1"
    api_key_env: "AGENT_BRIDGE_API_KEY"
    model: "ZHIPU/GLM-5.1"
    provider_api: "openai_chat"
    client_protocol: "codex_responses"
    reasoning_mode: "thinking"
```

交互式或脚本式配置时也可以指定：

```bash
agent-bridge configure --reasoning-mode thinking
```

`agent-bridge serve --reasoning-mode thinking` 可临时覆盖。

### 用户侧怎么调

在 Codex profile（`~/.codex/agent_bridge.config.toml`）里设置：

```toml
model = "ZHIPU/GLM-5.1"
model_provider = "agent_bridge"
model_reasoning_effort = "high"   # minimal|low|medium|high
```

Codex 会把这个值放进请求的 `reasoning.effort` 字段发给 AgentBridge，AgentBridge 再
按 provider 的 `reasoning_mode` 转换后转发给上游。用户**不需要安装额外脚本**，只要
通过 `agent-bridge run` / `agent-bridge start` 启动（已有的正常流程），映射就自动生效。

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

### Token 用量观测

AgentBridge 会自动向所有 OpenAI Chat Completions 兼容的上游请求流式 token 用量
（通过标准 `stream_options.include_usage`），并在 `/logs` 和 dashboard 里展示。

工作方式（能测就显示，不兼容不报错）：

- 代理对每个上游流式请求附加 `stream_options.include_usage = true`。
- 上游若支持，会在流的最后一个 chunk 里返回 `usage`（`prompt_tokens` /
  `completion_tokens` / `total_tokens`）。代理解析后写入请求日志和响应体。
- 上游若不支持或忽略该字段，请求照常完成，日志里 `token_usage.source` 显示为
  `unavailable`，**不会报错、不影响内容**。
- 字段命名同时兼容 OpenAI 风格（`prompt_tokens`）和 Anthropic 风格
  （`input_tokens`）。

`/logs` 里每条请求的 `token_usage` 字段示例：

```json
{
  "source": "upstream",
  "input_tokens": 10,
  "output_tokens": 6,
  "total_tokens": 16
}
```

`source` 取值：

| source        | 含义 |
|---------------|------|
| `upstream`    | 上游真实返回了 usage |
| `unavailable` | 上游未返回 usage（代理未做本地估算） |

已知会返回 token 用量的上游（流式 `include_usage`）：

| 上游 / 模型 | 是否返回 usage | 备注 |
|-------------|----------------|------|
| OpenAI 官方（gpt-4o / gpt-5 等） | 是 | 标准 `stream_options.include_usage` |
| 智谱 GLM（MOMA `moma.cmecloud.cn`，GLM-4.x / 5.x） | 视上游版本而定 | 以实际 `/logs` 里 `source` 为准 |
| 其他 OpenAI 兼容 provider | 视实现而定 | 不支持的自动降级为 `unavailable` |

如果你接入的上游确实返回了 usage，但在 `/logs` 里仍显示 `unavailable`，说明该
上游没有遵循 OpenAI 的 `include_usage` 约定。这不影响请求本身，只是 token 量
无法观测。

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
api_key_env: API_KEY
```

并确保环境变量存在。

### -p 切换 provider 后 model 没变

确保 `config.yaml` 中对应 provider 配置了正确的 `model` 字段。`agent-bridge run -p <provider>` 会自动将 provider 的 model 同步到 Codex profile，不需要手动编辑 `~/.codex/agent_bridge.config.toml`。

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
