# AgentBridge 阶段性过程计划

## 最终目标

把当前项目从单一 MOMA/Codex 代理升级为 AgentBridge：一个跨平台 agent gateway。

- 兼容 Windows 和 Linux。
- 一键安装代理、Codex CLI 和后续支持的 Claude Code 相关配置。
- 通过 `-p <平台>` 在启动时切换 API 供应商。
- 支持通过命令行临时配置自定义供应商。
- 区分两类协议：客户端需要的流协议，以及模型供应商暴露的 API 协议。
- 一条命令完成代理启动、健康检查、目标客户端启动。
- 实时监控代理状态，出现问题时输出可定位、可复盘的日志。
- 提供本地 UI 看板，查看每条请求日志、状态、错误和 token 用量。
- 对外产品名和主 CLI 先收敛为 `AgentBridge` / `agent-bridge`；Python 包名 `moma_proxy` 暂时保留，最终阶段再统一清理。

## 当前状态

- Codex 是第一优先级客户端。
- 当前可用链路是 `Codex /v1/responses -> moma_proxy -> MOMA /v1/chat/completions`。
- 已具备 Responses API 文本流基础能力。
- 已支持 OpenAI 标准 `delta.tool_calls` 解析和 Responses API function call 事件输出。
- 已验证 MOMA 上游使用标准 OpenAI `tool_calls` 格式，不需要额外 tool call parser 分支。
- 当前主要缺口是 `agent-bridge run` 一键启动、监控日志、UI 看板和 Claude Code/Anthropic 协议支持。
- 阶段 2 已提供跨平台安装入口；Claude Code 目前仅安装/检测 CLI，协议兼容仍属于后续阶段。
- 阶段 3 已提供 provider/protocol 配置抽象；当前只放行已实现的 `codex_responses -> openai_chat`。
- 阶段 3.5 已提前完成对外命名收敛：主 CLI 为 `agent-bridge`，兼容保留 `moma-proxy` 和 `moma`。

## 阶段 0：文档与边界收敛

状态：已完成（2026-06-19）。

目标：让后续 agent 和开发者明确项目方向、阶段顺序和当前边界。

产物：

- `AGENTS.md`：记录 agent 工作约束、产品方向和工程优先级。
- `PROGRESS.md`：记录阶段性计划和每阶段验收标准。
- README TODO：保留面向用户的高层待办，不展开实现细节。

验收：

- 新接手的人能从根目录文档判断当前目标、当前状态和下一阶段任务。
- 文档明确说明 Codex 是当前基线，Claude Code 是后续阶段。
- `.gitignore` 已忽略 `.venv/`、`venv/`、`env/`、`.conda/`、`conda-env/`，避免本地虚拟环境进入 Git。

## 阶段 1：稳定 Codex + MOMA 基线

状态：已完成（2026-06-19）。

目标：后续扩展不能破坏当前 Codex 通过 MOMA 使用 GLM 的能力。

重点：

- 保持 `/v1/responses` 到上游 Chat Completions 的转换稳定。
- 保持 streaming 输出、reasoning/content 分离、tool_calls 生命周期事件稳定。
- 补齐或维护覆盖 parser、transformer、OpenAI handler、Codex integration 的测试。
- 确认 `moma` wrapper 和 Codex profile 安装逻辑不会影响默认 Codex/OpenAI 配置。

验收：

- `pytest tests -v` 通过。
- Codex 通过 MOMA provider 能完成普通文本会话。
- Codex tool call 请求能被转换、流式返回，并进入下一轮 tool result。

完成记录：

- 已安装本地 `.venv` dev 依赖用于测试验收，虚拟环境目录已被 Git 忽略。
- 已完成全量测试：`29 passed`。
- 已完成本地 aiohttp 代理集成测试：chat completions streaming/non-streaming、Responses lifecycle events、Responses function tools bridge 均通过。
- 已确认 Codex profile 安装逻辑保留默认 Codex/OpenAI 配置，不会把全局默认切到 MOMA。

## 阶段 2：跨平台安装

状态：已完成（2026-06-19）。

目标：Windows 和 Linux 都能用一条安装命令准备代理和客户端环境。

重点：

- 检测 Python 版本、虚拟环境、包安装状态、Node/npm、Codex CLI。
- 安装或引导安装 Codex CLI；Claude Code 在支持阶段前只安装/检测 CLI，不标记协议已支持。
- npm 安装 Codex CLI 和 Claude Code CLI 时默认使用国内镜像 `https://registry.npmmirror.com`，并允许通过 `--npm-registry` 覆盖。
- 生成默认配置文件，不覆盖用户已有配置和 API key。
- 安装跨平台 launcher，避免硬编码 POSIX 路径和 shell 语法。
- 明确 Linux、Windows PowerShell 的安装命令和失败提示。

验收：

- Linux 环境能完成安装、配置生成和 Codex profile 注册。
- Windows 环境能完成同等安装流程，路径、环境变量和 launcher 可用。
- 重复执行安装命令不会覆盖 secrets，不会破坏已有 Codex 默认配置。

已完成：

- 新增 `agent-bridge install`，用于创建缺失配置、注册 Codex profile、检测 Node/npm/Codex/Claude Code；`moma-proxy install` 保留兼容。
- 新增 `--install-codex-cli`，缺失 Codex CLI 时可通过 npm 安装。
- 新增 `--install-claude-code`，缺失 Claude Code CLI 时可通过 npm 安装；这只代表 CLI 准备完成，不代表 Anthropic 协议已完成。
- 新增 `--npm-registry`，默认使用 `https://registry.npmmirror.com`，提高国内安装成功率。
- 已验证安装命令不会覆盖已有 `config.yaml`。
- 已验证 `agent-bridge install` 可在临时目录创建配置并输出工具检测结果。
- 已完成阶段测试：`35 passed`。

## 阶段 3：供应商与协议抽象

状态：已完成（2026-06-19）。

目标：支持 `-p <平台>` 选择供应商，并允许临时自定义供应商。

重点：

- 在配置中引入 provider 概念，包含名称、base URL、API key 环境变量、默认模型、供应商 API 协议、默认客户端协议。
- 将客户端协议和供应商 API 协议分开管理。
- 第一批客户端协议：Codex Responses stream。
- 后续客户端协议：Claude Code Anthropic stream。
- 第一批供应商协议：OpenAI Chat Completions。
- 后续供应商协议：OpenAI Responses、Anthropic Messages。
- CLI 支持启动时选择平台和传入临时 provider 参数。

示例目标：

```bash
agent-bridge run -p moma --client codex
agent-bridge run -p openai-compatible --base-url http://127.0.0.1:8000/v1 --model local-model
```

验收：

- `agent-bridge run -p moma --client codex` 使用配置中的 MOMA provider。
- 自定义 OpenAI-compatible provider 可以通过命令行临时启动。
- 不兼容的 client/provider protocol 组合会在启动前报错。

已完成：

- 新增 provider-aware 配置：`active_provider`、`default_model`、`providers.<name>`。
- provider 字段包含 `base_url`、`api_key`、`api_key_env`、`model`、`provider_api`、`client_protocol`。
- `serve` 和旧启动入口支持 `-p/--platform` 选择配置中的供应商。
- `serve` 支持通过 `--base-url`、`--api-key`、`--api-key-env`、`--model` 临时覆盖供应商。
- 已加入协议组合校验；当前只放行已实现的 `codex_responses -> openai_chat`。
- `config.yaml.example` 和 README 已补充多供应商配置示例。
- 已完成阶段测试：`42 passed`。

## 阶段 3.5：对外命名收敛

状态：已完成（2026-06-19）。

目标：先把产品和主 CLI 从 MOMA 专用命名中解耦，避免阶段 4 继续扩大命名混乱。

重点：

- 对外产品名使用 `AgentBridge`。
- 新增主 CLI：`agent-bridge`。
- 保留兼容 CLI：`moma-proxy`。
- 保留 `moma` 作为“用 MOMA profile 启动 Codex”的快捷命令。
- 暂不修改 Python 包名 `moma_proxy`、内部 import 和历史兼容配置。

验收：

- `agent-bridge install`、`agent-bridge serve` 后续作为主文档入口。
- `moma-proxy` 仍可兼容旧用法。
- 最终阶段明确包含 thorough code review、内部包名迁移评估、无用文件和死代码清理。
- 已验证 `.venv/bin/agent-bridge`、`.venv/bin/moma-proxy`、`.venv/bin/moma` 均存在。
- 已完成阶段测试：`43 passed`。

## 阶段 4：一条命令启动代理 + 客户端

状态：已完成（2026-06-19）。

目标：用户不需要手动开两个终端。

重点：

- `agent-bridge run` 作为日常入口。
- 启动代理为受控子进程或后台进程。
- 等待 `/health` 成功后再启动 Codex 或后续 Claude Code。
- 同一终端输出代理启动状态、端口冲突、配置错误和上游认证错误。
- 客户端退出后清理代理子进程。
- 保留 `python -m moma_proxy --config config.yaml` 作为调试入口。

验收：

- 一条命令能完成代理启动和 Codex 会话启动。
- 代理启动失败时，用户能看到明确原因。
- 客户端退出后不会留下无主代理进程。

已完成：

- 新增 `agent-bridge run`。
- `run` 会启动代理子进程、等待 `/health`、启动 Codex，并在客户端退出或失败时清理代理子进程。
- 支持 `-p/--platform` 和临时 provider 参数，复用阶段 3 的 provider/protocol 校验。
- 支持透传 Codex 参数，例如 `agent-bridge run -p moma --client codex exec "只输出 OK"`。
- 已覆盖 `agent-bridge run` 的代理启动、健康检查、客户端环境注入、退出清理和失败清理测试。

## 阶段 5：监控与结构化日志

状态：已完成（2026-06-19）。

目标：代理状态和请求问题可以实时发现、事后复盘。

重点：

- 为每个请求生成 request id。
- 结构化记录 provider、model、endpoint、client protocol、provider protocol、latency、status、stream 状态和错误详情。
- 记录代理进程和被拉起客户端的生命周期事件。
- 记录上游返回的 input/output token usage。
- 如果上游不返回 usage，不伪装成真实 token；只能标记为 unavailable，或单独记录 `estimated_input_tokens` / `estimated_output_tokens`。

验收：

- 日志能定位请求失败发生在客户端输入、协议转换、上游请求、stream parser 还是输出阶段。
- 日志能区分真实 token usage 和估算 token usage。
- 性能优化可以基于日志中的 latency 和错误分布推进。

已完成：

- 新增结构化请求日志和 request id。
- 支持透传或生成 `X-Request-ID`。
- 记录 method、path、status、latency、provider、model、endpoint、client protocol、provider protocol、stream state、error。
- 新增 `/logs` JSON 端点，供后续 UI 看板复用。
- token usage 当前明确标记为 `unavailable`，不伪装真实 usage。
- 已完成 warning-free 集成测试。

## 阶段 6：UI 看板

状态：已完成（2026-06-19）。

目标：用本地 dashboard 查看代理运行状态和每条日志。

重点：

- 展示代理健康状态、活跃请求、最近错误、请求历史。
- 展示每条请求的 provider、model、endpoint、状态、耗时、stream 状态。
- 展示 token usage，并标明来源是 upstream reported、estimated 还是 unavailable。
- 支持按 request id、provider、model、状态、错误筛选。
- 看板保持可选，不影响无头服务器或纯 CLI 使用。

验收：

- 打开本地看板即可看到实时请求日志。
- 每条日志可展开查看关键上下文和错误详情。
- token 字段不会把估算值误展示为真实上游 usage。

已完成：

- 新增 `/dashboard` 本地 HTML 看板。
- 看板读取 `/logs?limit=200` 并自动刷新。
- 展示 status、latency、endpoint、provider、model、protocols、stream state、token usage、request id、error。
- 支持按日志内容和状态段筛选。
- 已完成 dashboard 集成测试。

## 阶段 7：Claude Code 与 Anthropic 支持

状态：已完成（2026-06-19）。

目标：在 Codex 稳定后支持 Claude Code。

重点：

- 实现 Anthropic Messages 输入输出转换。
- 支持 Claude Code 需要的 streaming event。
- 支持 tool use 和 tool result 的双向转换。
- 复用 provider 抽象和 `agent-bridge run -p <平台> --client claude` 启动方式。

验收：

- Claude Code 能通过同一代理访问已配置 provider。
- Codex 现有测试和使用路径不回退。

已完成：

- 开放协议组合 `anthropic -> openai_chat`。
- 新增 `/v1/messages` Anthropic Messages endpoint。
- 支持 Anthropic text content、tool_result 输入到 Chat Completions messages 的转换。
- 支持 Anthropic tools 到 OpenAI function tools 的转换。
- 支持上游 `tool_calls` 转为 Anthropic `tool_use` streaming blocks。
- `agent-bridge run --client claude` 会启动代理并注入本地 `ANTHROPIC_BASE_URL`。
- 已完成 Anthropic transformer 和 `/v1/messages` 集成测试。

## 当前验收快照

状态：已完成阶段 4、5、6、7；按要求停在阶段 8 之前，尚未执行 thorough code review 和内部包名清理。

已验证：

- 触达文件格式检查：`black --check --workers 1 ...` 通过。
- import 排序检查：`isort --check-only ...` 通过。
- 全量测试：`57 passed`。

## 阶段 8：彻底命名与代码清理

触发条件：

- 至少支持一个非 MOMA 的 OpenAI-compatible provider。
- `agent-bridge run` 一键启动可用。
- 结构化日志和基础监控可用。
- 项目定位已经从 MOMA 专用代理变成多供应商 agent gateway。

工作内容：

- 做一次 thorough code review，重点审查命名、边界、无用分支、重复入口和历史兼容包袱。
- 决定是否把 Python 包名从 `moma_proxy` 迁移到 `agent_bridge`。
- 清理无用文件、过时代码分支、旧文档残留和不再需要的兼容逻辑。
- 保留必要迁移说明，避免破坏已有用户配置。

## 执行原则

- 先稳 Codex，再扩 Claude Code。
- 先抽象 provider/protocol，再做 UI 看板。
- 安装器和 launcher 必须从一开始考虑 Windows/Linux。
- 配置和安装流程不得覆盖用户已有 secrets。
- token usage 必须区分真实上游返回和本地估算。
- 每个阶段都要有可验证的验收结果，避免只完成结构不完成可用性。
