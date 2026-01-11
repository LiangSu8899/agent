# Changelog

## [V1.3.0] - 2026-01-10 (Phase 10)
### ✨ 新增特性 (Features)
- **Global Context Manager**: 引入 "Global Config + Local Context" 模式。支持自动检测项目目录 (`.agent/`)，跨目录打开项目，并保持独立的对话状态。
- **Global CLI**: 通过 `pip install -e .` 支持全局 `aos` 和 `agent-os` 命令。
- **State Persistence**: 自动记录并恢复上一次工作的项目路径。

### ⚡️ 改进 (Improvements)
- **Directory Management**: 启动时自动搜索项目配置文件，支持初始化新项目交互引导。

---

## [V1.2.0] - 2026-01-10 (Phase 9)
### ✨ 新增特性 (Features)
- **Hybrid Role Strategy**: 允许同时配置 `Planner` (规划者) 和 `Coder` (编码者) 角色，支持不同任务使用不同的模型组合。
- **Role Control Commands**: 
  - `/role`: 动态为角色分配模型。
  - `/roles`: 查看当前角色分配状态。
  - `/models`: 查看可用模型列表及详细计费信息。
- **Interactive Completion**: 增强了 Slash Commands 的自动补全功能，支持角色名和模型名的模糊匹配。

---

## [V1.1.0] - 2026-01-10 (Phase 8)
### ✨ 新增特性 (Features)
- **Interactive REPL**: 基于 `prompt_toolkit` 和 `rich` 的全新交互式终端。
  - 支持上下键翻阅历史命令。
  - 支持输入时的自动补全建议。
  - 漂亮的 Markdown 渲染和动态 Spinner 加载动画。
- **Slash Commands**: 新增 `/model`, `/cost`, `/clear` 等快捷指令，无需修改配置文件即可热切换模型。
- **Auto-Config**: 首次使用需鉴权的模型 (如 GPT-4) 时，REPL 会自动提示输入 API Key 并加密保存。

### ⚡️ 改进 (Improvements)
- **CLI**: `main.py` 默认行为改为启动 REPL，原单次执行模式保留。
- **Output**: 优化了长日志的流式展示体验，使用 Panel 组件隔离上下文。

---

## [V1.0.0] - 2026-01-10 (Phase 1-7)
### 🎉 首次发布 (Initial Release)
- **Core**: 完整的 Async Session 和 PTY 进程管理。
- **Brain**: 支持本地 GGUF 模型 (llama.cpp) 与 OpenAI 兼容接口的 Model Manager。
- **Memory**: 基于 SQLite 的错误记忆与去重机制。
- **Safety**: Git 自动 Checkpoint 与回滚机制。
- **Tools**: 集成 FileEditor, GitHandler, DockerTool, BrowserTool。
