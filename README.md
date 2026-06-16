# MOMA Proxy

MOMA 平台 GLM-5.1 到 Codex/Anthropic 协议转换的 API 代理。

## 问题背景

MOMA 平台的 GLM-5.1 模型在 streaming 输出时会先输出 `reasoning_content`（推理过程），再输出 `content`（实际回复）。标准 OpenAI 协议不包含 reasoning 字段，导致常规代理无法正确解析。

## 解决方案

本代理：
1. 接收标准 OpenAI 格式请求
2. 转发到 GLM 平台
3. 解析 GLM 的非标准 streaming 输出（过滤 reasoning）
4. 返回 Codex 兼容的 OpenAI 格式响应

## 快速开始

### 1. 安装

```bash
# 创建 conda 环境
conda create -n moma_proxy python=3.11 -y
conda activate moma_proxy

# 安装依赖
pip install -e ".[dev]"
```

### 2. 配置

复制配置模板并修改：

```bash
cp config.yaml.example config.yaml
```

配置文件示例：

```yaml
upstream:
  base_url: "https://moma.cmecloud.cn/v1"
  api_key: "your-api-key"

server:
  host: "0.0.0.0"
  port: 8080

mode: "codex"

logging:
  level: "INFO"
```

### 3. 启动

```bash
cd /root/moma_proxy && conda activate moma_proxy && python -m moma_proxy --config config.yaml
```

### 4. 使用

代理启动后，将你的 API 请求发送到代理地址而非 GLM 平台直连：

```bash
# 原本直接调用 GLM
curl https://moma.cmecloud.cn/v1/chat/completions ...

# 现通过代理调用（过滤掉 reasoning，只返回 content）
curl http://localhost:8080/v1/chat/completions ...
```

**请求示例（Chat Completions）：**

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

**请求示例（Responses API - ccswitch）：**

```bash
curl -X POST "http://localhost:8080/v1/responses" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ZHIPU/GLM-5.1",
    "input": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

**请求示例（Responses API - Codex 多模态格式）：**

```bash
curl -X POST "http://localhost:8080/v1/responses" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ZHIPU/GLM-5.1",
    "input": [{"role": "user", "content": [{"text": "你好"}]}],
    "stream": true
  }'
```

**格式转换说明：** `/v1/responses` 端点会自动将 Codex 的多模态格式（数组）转换为 GLM 平台所需的简单字符串格式。

**响应示例：**

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","model":"ZHIPU/GLM-5.1","choices":[{"index":0,"delta":{"content":"你好"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","model":"ZHIPU/GLM-5.1","choices":[{"index":0,"delta":{"content":"！"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","model":"ZHIPU/GLM-5.1","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## 端点说明

| 端点 | 说明 |
|------|------|
| `/v1/chat/completions` | Chat completions（OpenAI 格式） |
| `/v1/completions` | Legacy completions（转换为 chat 格式） |
| `/v1/responses` | Responses API（ccswitch 兼容，转换为 chat 格式） |
| `/health` | 健康检查 |

**性能优化：** `/v1/responses` 端点已优化，响应时间约 4-5秒（GLM-5.1 上游处理为主）。

## 在客户端中使用

将客户端的 API base URL 改为代理地址：

```python
# Python OpenAI SDK
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="any-key"  # 代理会使用配置文件中的 upstream api_key
)

response = client.chat.completions.create(
    model="ZHIPU/GLM-5.1",
    messages=[{"role": "user", "content": "你好"}],
    stream=True
)

for chunk in response:
    print(chunk.choices[0].delta.content)
```

## 在 Codex 中使用 MOMA

本项目会把 MOMA 注册成 Codex 的独立 profile，同时保留默认 `codex` 继续走 OpenAI/GPT。

### 安装 Codex profile

安装或更新 Codex 的 MOMA provider/profile：

```bash
moma-proxy install-codex
```

安装后：

- 默认 Codex：运行 `codex`，仍走默认 GPT。
- MOMA Codex：运行 `moma`，等价于带环境变量执行 `codex -p moma`。

如果你的代理不是 `127.0.0.1:8080`，安装时指定地址：

```bash
moma-proxy install-codex --base-url http://127.0.0.1:9000/v1
```

该命令会写入以下配置：

`~/.codex/config.toml` 保留默认模型，同时注册本地代理 provider：

```toml
[model_providers.moma_proxy]
name = "MOMA Proxy"
base_url = "http://127.0.0.1:8080/v1"
env_key = "MOMA_PROXY_API_KEY"
wire_api = "responses"
```

`~/.codex/moma.config.toml` 只负责切换模型和 provider：

```toml
model = "ZHIPU/GLM-5.1"
model_provider = "moma_proxy"
```

Codex 要求自定义 provider 的 `env_key` 存在。`moma` 命令会自动注入这个客户端侧 key；代理会忽略它，真实 MOMA key 来自本项目的 `config.yaml`。

### 启动和验证

```bash
# 启动代理
cd /root/moma_proxy && conda activate moma_proxy && python -m moma_proxy --config config.yaml
```

另开一个终端使用 MOMA Codex：

```bash
moma
```

验证非交互调用：

```bash
moma exec -C /root/moma_proxy "只输出 OK 两个字母，不要解释。"
```

输出中应能看到：

```text
model: ZHIPU/GLM-5.1
provider: mycodex
codex
OK
```

默认 GPT Codex 仍然使用：

```bash
codex
```

也可以直接验证 Responses API：

```bash
curl -sS http://127.0.0.1:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"model":"ZHIPU/GLM-5.1","input":[{"role":"user","content":"hello"}],"stream":true}'
```

### 回滚方式

如果 MOMA profile 不可用，不要把默认 Codex 改成 MOMA。先继续用默认 GPT：

```bash
codex
```

如需彻底恢复 Codex 配置，使用最近的备份覆盖：

```bash
cp /root/.codex/config.toml.bak-before-profile-20260615-234703 /root/.codex/config.toml
```

如果没有这个备份，手动把 `/root/.codex/config.toml` 开头改回：

```toml
model = "gpt-5.5"
model_provider = "openai"
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

## 配置选项

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `upstream.base_url` | GLM 平台 API 地址 | 必填 |
| `upstream.api_key` | GLM 平台 API 密钥 | 必填 |
| `server.host` | 代理服务监听地址 | `0.0.0.0` |
| `server.port` | 代理服务端口 | `8080` |
| `mode` | 输出协议模式 | `codex` |
| `logging.level` | 日志级别 | `INFO` |

## TODO

- [x] `/v1/responses` 端点支持（ccswitch 兼容）
- [x] 性能优化（响应时间优化至 4.8秒）
- [x] MOMA 工具调用格式验证（标准 OpenAI tool_calls）
- [ ] Anthropic 协议支持（Claude Code 兼容）
