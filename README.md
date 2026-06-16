# MOMA Proxy

将 GLM-5.1 非标准 streaming 输出转换为 Codex 兼容的 Responses API 格式的代理。

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

### 1. 安装代理

```bash
# 克隆仓库
git clone https://github.com/STEVE-1936550490/MoMa_proxy.git
cd MoMa_proxy

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate   # ⚠️ 每次使用前都需要激活

# 或使用 conda
# conda create -n moma_proxy python=3.11 -y
# conda activate moma_proxy

# 安装依赖
pip install -e ".[dev]"
```

### 2. 配置

复制配置模板并填入你的 API Key：

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`：

```yaml
upstream:
  base_url: "https://moma.cmecloud.cn/v1"
  api_key: "${MOMA_API_KEY}"   # 推荐使用环境变量，也可直接填入 key

server:
  host: "0.0.0.0"
  port: 8080

mode: "codex"

logging:
  level: "INFO"
```

**安全提示：** `config.yaml` 已在 `.gitignore` 中排除，不会被提交到 Git。推荐使用环境变量方式配置 API Key：

```bash
export MOMA_API_KEY="your-api-key-here"
```

### 3. 启动代理

```bash
source .venv/bin/activate   # 激活虚拟环境
python -m moma_proxy --config config.yaml
```

验证代理是否正常运行：

```bash
curl http://localhost:8080/health
# 应返回 {"status": "healthy"}
```

### 4. 在 Codex 中使用（可选）

如果你想让 Codex 通过此代理使用 GLM-5.1：

```bash
# 确保 Codex CLI 已安装
npm install -g @openai/codex

# 激活虚拟环境
source .venv/bin/activate

# 一键注册 MOMA profile 到 Codex
moma-proxy install-codex

# 使用 MOMA Codex
source .venv/bin/activate
moma

# 默认 Codex（GPT）不受影响
codex
```

> **⚠️ 提醒：** `moma`、`moma-proxy` 等命令都安装在虚拟环境中，每次使用前需要 `source .venv/bin/activate`，否则会提示 command not found。

如果你的代理不在默认地址 `127.0.0.1:8080`：

```bash
moma-proxy install-codex --base-url http://127.0.0.1:9000/v1
```

## 端点说明

| 端点 | 说明 |
|------|------|
| `/v1/chat/completions` | Chat Completions（OpenAI 格式） |
| `/v1/completions` | Legacy Completions（自动转换为 chat 格式） |
| `/v1/responses` | Responses API（Codex 兼容，含 tool_calls 支持） |
| `/v1/models` | 模型列表 |
| `/health` | 健康检查 |

## 请求示例

**Chat Completions：**

```bash
curl -X POST "http://localhost:8080/v1/chat/completions" \
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
curl -X POST "http://localhost:8080/v1/responses" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ZHIPU/GLM-5.1",
    "input": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

**Python SDK：**

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
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

## CLI 命令

```bash
# 激活虚拟环境（每次使用前必须执行）
source .venv/bin/activate

# 启动代理服务器
moma-proxy serve --config config.yaml
# 或直接
python -m moma_proxy --config config.yaml

# 安装 Codex MOMA profile
moma-proxy install-codex [--base-url URL] [--codex-home PATH]

# 通过 MOMA 启动 Codex
moma
# 等价于 codex -p moma，自动注入客户端侧 API key
```

## 配置选项

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `upstream.base_url` | GLM 平台 API 地址 | 必填 |
| `upstream.api_key` | GLM 平台 API 密钥，支持 `${ENV_VAR}` 环境变量展开 | 必填 |
| `server.host` | 代理服务监听地址 | `0.0.0.0` |
| `server.port` | 代理服务端口 | `8080` |
| `mode` | 输出协议模式：`codex` 或 `anthropic`（暂未实现） | `codex` |
| `logging.level` | 日志级别 | `INFO` |

## 项目结构

```
src/moma_proxy/
├── __init__.py
├── __main__.py          # python -m 入口
├── main.py              # CLI 入口（serve / install-codex / codex）
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
    └── anthropic.py     # Anthropic 格式转换（TODO）
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
- [ ] Anthropic 协议支持（Claude Code 兼容）

## License

MIT
