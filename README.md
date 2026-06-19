# AgentBridge

AgentBridge 是一个面向 Codex / Claude Code 等编程 agent 的本地模型供应商网关。当前 Python 包名和兼容命令仍保留为 `moma-proxy`，但主推 CLI 是 `agent-bridge`。

当前首个稳定场景：将 MOMA 平台 GLM-5.1 非标准 streaming 输出转换为 Codex 兼容的 Responses API 格式。

## 问题背景

MOMA 平台的 GLM-5.1 模型在 streaming 输出时会先输出 `reasoning_content`（推理过程），再输出 `content`（实际回复）。标准 OpenAI 协议不包含 reasoning 字段，导致常规代理无法正确解析。

## 解决方案

本代理：
1. 接收标准 OpenAI / Responses API 格式请求
2. 转发到 GLM 平台
3. 解析 GLM 的非标准 streaming 输出（过滤 reasoning）
4. 返回 Codex 兼容的 Responses API 格式响应

## 前置依赖

| 依赖 | 安装方式 | 用途 |
|------|----------|------|
| **Python ≥ 3.11** | 系统包管理器或 conda | 运行代理 |
| **Codex CLI** | `npm install -g @openai/codex` | 如果你需要用 `moma` 命令在 Codex 中使用 GLM |
| **MOMA 平台 API Key** | 在 MOMA 平台申请 | 访问 GLM-5.1 模型 |

> **注意：** Codex CLI 是可选的。如果你只用 Python SDK 或 curl 调用代理，不需要安装 Codex。

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/STEVE-1936550490/MoMa_proxy.git
cd MoMa_proxy
```

### 2. 创建虚拟环境（二选一）

#### 方案 A：Anaconda（推荐 ✅）

Conda 环境是全局注册的，激活后**在任何目录下**都可以直接使用 `agent-bridge`、`moma-proxy`、`moma` 等命令，无需每次 cd 到项目目录。

```bash
conda create -n moma_proxy python=3.11 -y
conda activate moma_proxy
pip install -e ".[dev]"
```

#### 方案 B：venv

venv 是项目本地虚拟环境，**每次使用前都必须先 cd 到项目目录再激活**，否则找不到已安装的命令。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

> 💡 **选哪个？** 如果你已安装 Anaconda/Miniconda，强烈推荐方案 A。Conda 环境激活后全局可用，不需要记住项目路径；venv 则要求你每次先 `cd MoMa_proxy && source .venv/bin/activate` 才能使用。

### 3. 配置

推荐先运行本地安装检查；它会创建缺失的 `config.yaml`、注册 Codex profile，并检测 Node/npm、Codex CLI、Claude Code：

```bash
agent-bridge install
```

如果需要自动安装 Codex CLI 或 Claude Code CLI，可以显式开启。npm 默认使用国内镜像 `https://registry.npmmirror.com`，也可以用 `--npm-registry` 覆盖：

```bash
agent-bridge install --install-codex-cli
agent-bridge install --install-codex-cli --install-claude-code
agent-bridge install --npm-registry https://registry.npmjs.org
```

> Claude Code CLI 已支持通过本地 `/v1/messages` 兼容入口连接当前 OpenAI Chat Completions provider；如果你只使用 Codex，可以不安装 Claude Code CLI。

也可以手动复制配置模板并填入你的 API Key：

```bash
cp config.yaml.example config.yaml
```

或者使用交互式配置命令：

```bash
agent-bridge configure --config config.yaml
```

也可以用命令行一次写入配置，适合脚本或远程机器初始化：

```bash
agent-bridge configure --config config.yaml --no-interactive \
  --provider moma_glm51 \
  --base-url "https://moma.cmecloud.cn/v1" \
  --api-key-env MOMA_API_KEY \
  --model "ZHIPU/GLM-5.1" \
  --provider-api openai_chat \
  --client-protocol codex_responses
```

`configure` 默认会同步 Codex 的 `moma` profile 到当前本地代理地址和模型；如只想写 `config.yaml`，可加 `--skip-codex-profile`。

编辑 `config.yaml`：

```yaml
upstream:
  base_url: "https://moma.cmecloud.cn/v1"
  api_key: "${MOMA_API_KEY}"   # 推荐使用环境变量，也可直接填入 key

server:
  host: "0.0.0.0"
  port: 17681

mode: "codex"

logging:
  level: "INFO"
```

如果要启用多供应商配置，可以在 `config.yaml` 中使用 `providers`，然后启动时用 `-p` 选择：

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
```

当前已实现的协议组合是 `codex_responses -> openai_chat` 和 `anthropic -> openai_chat`。`openai_responses`、`anthropic_messages` 等供应商 API 协议已预留配置字段，但会在后续阶段实现。

**安全提示：** `config.yaml` 已在 `.gitignore` 中排除，不会被提交到 Git。推荐使用环境变量方式配置 API Key：

```bash
# 写入 ~/.bashrc 永久生效（重启终端、git pull 更新后都无需重新设置）
echo 'export MOMA_API_KEY="your-api-key-here"' >> ~/.bashrc
source ~/.bashrc
```

> 如果不想写 bashrc，也可以直接把 key 填入 `config.yaml` 的 `api_key` 字段（明文，仅限本地开发使用）。

### 4. 启动代理

| 环境 | 命令 |
|------|------|
| **Conda** | `conda activate moma_proxy && python -m moma_proxy --config config.yaml` |
| **venv** | `cd /path/to/MoMa_proxy && source .venv/bin/activate && python -m moma_proxy --config config.yaml` |

指定配置中的供应商：

```bash
agent-bridge serve --config config.yaml -p moma_glm51
```

临时使用 OpenAI-compatible 供应商：

```bash
agent-bridge serve \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key-env LOCAL_API_KEY \
  --model local-model \
  --provider-api openai_chat \
  --client-protocol codex_responses
```

验证代理是否正常运行：

```bash
curl http://localhost:17681/health
# 应返回 {"status": "healthy"}
```

日常使用可以直接读取 `config.yaml` 的 `active_provider`，启动代理并进入 Codex：

```bash
agent-bridge
```

等价的显式命令：

```bash
agent-bridge start
```

如果需要指定 provider 或传入更多参数，可以继续使用完整入口：

```bash
agent-bridge run -p moma_glm51 --client codex
```

也可以把参数透传给 Codex，例如非交互执行：

```bash
agent-bridge run -p moma_glm51 --client codex exec "只输出 OK"
```

启动代理并进入 Claude Code：

```bash
agent-bridge run -p moma_glm51 --client claude
```

`run` 会启动代理、等待 `/health` 成功、再启动客户端；客户端退出后会清理代理子进程。

### 5. 在 Codex 中使用（可选）

如果你想让 Codex 通过此代理使用 GLM-5.1，需要完成以下两步：

#### 第一步：安装（只需做一次）

确保已安装 Codex CLI，并注册 MOMA profile：

| 环境 | 命令 |
|------|------|
| **Conda** | `conda activate moma_proxy && npm install -g @openai/codex && agent-bridge install-codex` |
| **venv** | `cd /path/to/MoMa_proxy && source .venv/bin/activate && npm install -g @openai/codex && agent-bridge install-codex` |

国内网络优先使用 npm 镜像：

```bash
npm install -g @openai/codex --registry https://registry.npmmirror.com
```

如果你的代理不在默认地址 `127.0.0.1:17681`：

```bash
agent-bridge install-codex --base-url http://127.0.0.1:9000/v1
```

#### 第二步：日常使用（每次启动 Codex 时）

| 环境 | 命令 |
|------|------|
| **Conda** | `conda activate moma_proxy && moma` |
| **venv** | `cd /path/to/MoMa_proxy && source .venv/bin/activate && moma` |

> 默认 Codex（GPT）不受影响，仍通过 `codex` 命令使用。

#### Codex 模型元数据提示

使用 `ZHIPU/GLM-5.1` 等非 OpenAI 官方模型时，Codex 可能输出类似提示：

```text
Model metadata for `ZHIPU/GLM-5.1` not found. Defaulting to fallback metadata; this can degrade performance and cause issues.
```

这是 Codex 本地没有内置该模型的 metadata，因而回退到默认模型信息；不是 AgentBridge 配置错误，也不是 API key 或上游 URL 错误。只要请求能正常返回内容，这个提示通常可以忽略。

## 端点说明

| 端点 | 说明 |
|------|------|
| `/v1/chat/completions` | Chat Completions（OpenAI 格式） |
| `/v1/completions` | Legacy Completions（自动转换为 chat 格式） |
| `/v1/responses` | Responses API（Codex 兼容，含 tool_calls 支持） |
| `/v1/messages` | Anthropic Messages（Claude Code 兼容基础，含 tool_use 支持） |
| `/v1/models` | 模型列表 |
| `/health` | 健康检查 |
| `/logs` | 最近结构化请求日志 |

## 观测与日志

AgentBridge 会为每个请求生成或透传 `X-Request-ID`，并记录结构化日志字段：

- request id、method、path、status、latency
- provider、model、client protocol、provider protocol
- stream state、error
- token usage 来源：`upstream` / `estimated` / `unavailable`

查看最近日志：

```bash
curl http://localhost:17681/logs
curl http://localhost:17681/logs?limit=20
```

当前 token usage 默认标记为 `unavailable`；只有上游返回真实 usage 或后续估算逻辑明确接入时，才会显示对应来源。

打开本地看板：

```text
http://localhost:17681/dashboard
```

看板会自动刷新 `/logs`，支持按 request id、provider、model、path、status、error 筛选。

## 请求示例

**Chat Completions：**

```bash
curl -X POST "http://localhost:17681/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ZHIPU/GLM-5.1",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true,
    "max_tokens": 100
  }'
```

**Responses API（Codex 格式）：**

```bash
curl -X POST "http://localhost:17681/v1/responses" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ZHIPU/GLM-5.1",
    "input": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

**Anthropic Messages（Claude Code 格式）：**

```bash
curl -X POST "http://localhost:17681/v1/messages" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ZHIPU/GLM-5.1",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 100,
    "stream": true
  }'
```

**Python SDK：**

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:17681/v1",
    api_key="any-key"  # 代理使用 config.yaml 中的 upstream api_key
)

response = client.chat.completions.create(
    model="ZHIPU/GLM-5.1",
    messages=[{"role": "user", "content": "你好"}],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

## CLI 命令速查

### Conda 环境

```bash
# 启动代理
conda activate moma_proxy && python -m moma_proxy --config config.yaml

# 安装 Codex MOMA profile（只需一次）
conda activate moma_proxy && agent-bridge install-codex

# 一键本地安装检查，默认使用 npm 国内镜像安装可选 CLI
conda activate moma_proxy && agent-bridge install --install-codex-cli

# 启动 MOMA Codex
conda activate moma_proxy && moma

# 一条命令启动代理 + Codex（读取 config.yaml 的 active_provider）
conda activate moma_proxy && agent-bridge

# 一条命令启动代理 + Claude Code
conda activate moma_proxy && agent-bridge run -p moma_glm51 --client claude
```

### venv 环境

```bash
# 启动代理
cd /path/to/MoMa_proxy && source .venv/bin/activate && python -m moma_proxy --config config.yaml

# 安装 Codex MOMA profile（只需一次）
cd /path/to/MoMa_proxy && source .venv/bin/activate && agent-bridge install-codex

# 一键本地安装检查，默认使用 npm 国内镜像安装可选 CLI
cd /path/to/MoMa_proxy && source .venv/bin/activate && agent-bridge install --install-codex-cli

# 启动 MOMA Codex
cd /path/to/MoMa_proxy && source .venv/bin/activate && moma

# 一条命令启动代理 + Codex（读取 config.yaml 的 active_provider）
cd /path/to/MoMa_proxy && source .venv/bin/activate && agent-bridge

# 一条命令启动代理 + Claude Code
cd /path/to/MoMa_proxy && source .venv/bin/activate && agent-bridge run -p moma_glm51 --client claude
```

## 配置选项

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `upstream.base_url` | GLM 平台 API 地址 | 必填 |
| `upstream.api_key` | GLM 平台 API 密钥，支持 `${ENV_VAR}` 环境变量展开 | 必填 |
| `active_provider` | 默认供应商名称，用于 `providers` 配置 | `None` |
| `default_model` | 未传入请求模型时使用的默认模型 | `ZHIPU/GLM-5.1` |
| `providers.<name>.base_url` | 供应商 API 地址 | 可选 |
| `providers.<name>.api_key_env` | 供应商 API Key 环境变量名 | 可选 |
| `providers.<name>.model` | 供应商默认模型 | `ZHIPU/GLM-5.1` |
| `providers.<name>.provider_api` | 供应商 API 协议：`openai_chat` / `openai_responses` / `anthropic_messages` | `openai_chat` |
| `providers.<name>.client_protocol` | 客户端协议：`codex_responses` / `anthropic` | `codex_responses` |
| `server.host` | 代理服务监听地址 | `0.0.0.0` |
| `server.port` | 代理服务端口 | `17681` |
| `mode` | 输出协议模式：`codex` 或 `anthropic`（暂未实现） | `codex` |
| `logging.level` | 日志级别 | `INFO` |

## 项目结构

```
src/moma_proxy/
├── __init__.py
├── __main__.py          # python -m 入口
├── main.py              # CLI 入口（configure / install / serve / start / run / install-codex / codex）
├── server.py            # aiohttp 服务器
├── config.py            # YAML 配置加载，支持环境变量展开
├── codex.py             # Codex profile 安装与启动逻辑
├── codex_cli.py         # `moma` 命令入口
├── handlers/
│   └── openai.py        # OpenAI / Responses API 协议处理器
├── parsers/
│   └── glm.py           # GLM-5.1 流解析器（分离 reasoning/content/tool_call）
└── transformers/
    ├── codex.py         # Chat Completions 格式转换
    ├── responses.py     # Responses API 格式转换（含 tool_calls 生命周期事件）
    └── anthropic.py     # Anthropic Messages 格式转换
```

## 开发

```bash
# 运行测试
pytest tests -v

# 运行单个测试
pytest tests/test_parser.py -v

# 格式化代码
black src tests
isort src tests

# 类型检查
mypy src
```

## TODO

- [x] `/v1/responses` 端点支持（Codex 兼容）
- [x] 性能优化（响应时间优化至 4.8 秒）
- [x] MOMA 工具调用格式验证（标准 OpenAI tool_calls）
- [x] Anthropic 协议支持（Claude Code 兼容基础）
- [x] 一键启动：`agent-bridge` / `agent-bridge start` / `agent-bridge run` 同时拉起代理 + Codex/Claude Code，无需手动开两个终端

## License

MIT
