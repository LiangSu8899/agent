# Agent Debug OS

> **一个面向真实工程调试场景的 Agent Runtime，而不是聊天机器人**  
> A Debug‑First Agent Runtime for Real‑World Engineering Tasks

---

## 📌 项目简介 | Project Overview

**Agent Debug OS** 是一个以「调试优先（Debug‑First）」为核心设计理念的 Agent 框架，专门用于：

- 长时间运行任务（Docker build / CI / 编译）
- 可中断 / 可恢复的会话执行
- 自动错误识别与修复尝试
- 严格的状态管理与失败记忆
- 本地 / API 大模型的灵活切换

它并不是一个传统的“对话型 Agent”，而是更接近一个：

> 🧠 **为工程师服务的调试操作系统（Debug Operating System）**

---

**Agent Debug OS** is a *debug‑first* agent runtime designed for **real engineering workflows**, not chat demos.

It focuses on:

- Long‑running tasks (Docker builds, CI, compilation)
- Interruptible & resumable execution
- Automatic error detection and recovery
- Persistent session & failure memory
- Flexible local / API‑based LLM usage

> Think of it as an **Operating System for Debugging**, not a chatbot.

---

## 🧱 核心设计理念 | Core Design Philosophy

### 1️⃣ Session First（会话优先）
- 每个任务都是一个 **Session**
- Session 拥有独立状态与持久化存储（SQLite）
- 支持：`Created → Running → Paused → Completed / Failed`

### 2️⃣ Real Terminal, Not subprocess
- 基于 **PTY (Pseudo‑Terminal)**
- 支持真实 Shell 行为（attach / detach）
- 适合 Docker、编译器、交互式命令

### 3️⃣ Debug Loop, Not Prompt Loop
- 观察输出（stdout/stderr）
- 识别错误类型
- 查询历史失败，避免重复修复
- 决策下一步操作

### 4️⃣ Safety by Design
- 所有代码修改都有 Git 快照
- 支持 diff 预览与回滚
- Agent 的失败是**可审计、可恢复的**

---

## 📁 项目结构 | Project Structure

```text
agent/
├── agent_core/          # 核心运行时（Session / Terminal / Agent）
│   ├── session.py
│   ├── terminal.py
│   ├── models.py
│   ├── memory.py
│   └── agent.py
│
├── agent_tools/         # 工具层（文件 / Git / Docker / Browser）
│   ├── file_editor.py
│   ├── git_handler.py
│   ├── docker_tool.py
│   └── browser_tool.py
│
├── tests/               # 分阶段验收测试
│   ├── phase1_verify.py
│   ├── phase2_verify.py
│   └── ...
│
├── sandbox_test/        # 文件/代码修改测试沙盒
├── config.yaml          # Agent & 模型配置
├── sessions.db          # Session 状态数据库
└── main.py              # 启动入口
```

---

## 🚀 快速开始 | Quick Start

### 1️⃣ 克隆项目

```bash
git clone https://github.com/LiangSu8899/agent.git
cd agent
```

### 2️⃣ 安装依赖

```bash
pip install -r requirements.txt
```

> 若暂无 `requirements.txt`，请至少安装：
```bash
pip install openai transformers tiktoken pyyaml
```

### 3️⃣ 配置模型 | Configure Model

编辑 `config.yaml`：

```yaml
model:
  provider: openai        # openai / local
  name: gpt-4o-mini
```

或使用本地模型：

```yaml
model:
  provider: local
  backend: llama.cpp
  model_path: ./models/coder-7b.gguf
```

并设置环境变量（如使用 API）：

```bash
export OPENAI_API_KEY="your_api_key"
```

---

## ▶️ 运行示例 | Run Example

### 启动 Agent

```bash
python main.py
```

### 启动一个调试 Session（示例）

```python
from agent_core.session import Session

session = Session.create(
    command="for i in {1..5}; do echo $i; sleep 1; done"
)
session.start_async()
```

支持：
- attach / detach
- pause / resume
- 日志持久化

---

## 🧪 测试 | Testing

项目采用 **分 Phase 验收测试**：

```bash
python tests/phase1_verify.py
python tests/phase2_verify.py
```

每个 Phase 都验证一个关键能力：

| Phase | 能力 |
|------|------|
| Phase 1 | Session + PTY 长任务 |
| Phase 2 | 本地模型管理 |
| Phase 3 | 调试循环与失败记忆 |
| Phase 4 | 文件修改与回滚 |
| Phase 5 | Docker / Browser 工具 |

---

## 🧠 适用场景 | Use Cases

- Docker build / CI 调试
- 复杂项目依赖错误修复
- 本地大模型辅助工程调试
- Agent 研究 / Debug Agent 原型

---

## ⚠️ 当前状态 | Project Status

- 🚧 **Active Development**
- 当前以工程验证与架构稳定性为优先
- 尚未承诺 API 稳定性

欢迎 Issue / PR / 讨论。

---

## 📜 License

MIT License

---

## 🙌 致谢 | Acknowledgements

- 灵感来自真实工程调试流程
- 设计目标：**让 Agent 像一个可靠的工程师，而不是话多的聊天机器人**

---

如果你也是工程师，并且厌倦了“只会聊天不会干活”的 Agent ——

**这个项目就是为你准备的。**

