# Changelog

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
