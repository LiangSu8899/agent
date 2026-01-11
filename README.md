# DebugFlow (V1.3)

<p align="center">
  <a href="README_EN.md">English</a> | <a href="README.md">中文</a>
</p>

> **一个面向真实工程调试场景的 Agent Runtime，更是一个“工程化的 DebugFlow 雏形”。**  
> A Engineering-Grade DebugFlow Prototype for Real-World Debugging.

---

## 📌 系统架构 (System Architecture)

DebugFlow 不是线性的 LLM 问答，而是一个**基于状态机（State Machine）的闭环控制系统**。

```mermaid
graph TD
    User[User] -->|CLI Commands| Main[Main Entrypoint]

    Main -->|Init| Orch[Orchestrator]

    subgraph DebugFlow_Runtime
        Orch -->|Manage| Session[Session]
        Orch -->|Manage| Agent[DebugAgent]

        Session <-->|Stdin Stdout| Terminal[RealTerminal]

        Agent -->|Observe| Observer[OutputObserver]
        Observer -->|Parse Logs| Terminal

        Agent -->|Think| Brain[ModelManager]
        Brain -->|Load Unload| LLM[LLMModels]

        Agent -->|Recall| Memory[HistoryMemory]

        Agent -->|Act| Tools[Toolbox]
    end

    subgraph Toolbox
        Tools --> Git[GitHandler]
        Tools --> File[FileEditor]
        Tools --> Docker[DockerTool]
        Tools --> Browser[BrowserTool]
    end

    Git -->|Checkpoint| FileSystem
    File -->|Modify| FileSystem
```

---

## 🧱 核心模块说明

| 模块 | 职责 | 关键特性 |
| --- | --- | --- |
| **Session** | 任务运行时容器 | 异步、支持 PTY (伪终端)、可暂停/恢复、日志持久化 |
| **Orchestrator** | 总指挥 | 协调 Agent 与 Session，处理用户信号 (Ctrl+C)，管理生命周期 |
| **ModelManager** | 算力调度 | 显存互斥管理 (自动 Unload)、Token 计数、多后端支持 (Local/API) |
| **HistoryMemory** | 经验库 | 记录 `(Command, Error, Result)`，防止 Agent 陷入死循环 |
| **GitHandler** | 安全网 | 任何文件修改前强制 Commit，提供 `reset --hard` 回滚能力 |
| **Observer** | 感知器 | 实时流式分析终端输出，正则匹配错误类型 |

---

## 🚀 快速开始 (Quick Start)

### 1. 环境准备

```bash
# 1. 克隆项目
git clone https://github.com/LiangSu8899/agent.git agent-os
cd agent-os

# 2. 创建虚拟环境 (推荐 Python 3.10+)
python -m venv venv
source venv/bin/activate

# 3. 安装依赖与全局命令
pip install -r requirements.txt
pip install -e .
# 核心依赖：llama-cpp-python, duckduckgo-search, gitpython, docker, tiktoken, openai
```

---

## 📁 项目管理与启动指南 (New in V1.3)

Agent OS 采用 "Global Config + Local Context" 的管理模式（类似 Git 或 VS Code）。

### 1. 启动逻辑
Agent 会根据你所在的目录自动判断上下文：

- **场景 A：进入现有项目**
  ```bash
  cd ~/my-backend-project
  aos
  ```
  **系统行为**：检测到当前目录存在 `.agent/` 文件夹。  
  **结果**：直接加载该项目的历史记录和 Session，状态栏显示 `[Proj: my-backend-project]`。

- **场景 B：初始化新项目**
  ```bash
  mkdir new-app && cd new-app
  aos
  ```
  **系统行为**：检测到当前目录没有 `.agent/` 文件夹。  
  **交互提示**：
  ```plaintext
  No project found in current directory.
  [1] Initialize new project here? (.agent/)
  [2] Open last project: /home/user/old-project
  [3] Exit
  > 
  ```
  选择 `1`：会在当前目录创建 `.agent/`，并初始化独立的数据库。

- **场景 C：快速打开上次工作区**
  无论你在哪个目录（例如 `~`）：
  ```bash
  aos
  # 选择 [2] Open last project
  ```
  **结果**：Agent 会自动切换工作目录（chdir）到上一次的项目路径，并加载该环境。

### 2. 配置文件位置

| 配置文件路径 | 作用 |
| --- | --- |
| `~/.agent_os/config.yaml` | **全局配置**：存放 API Keys、模型定义、默认角色设置。所有项目共用。 |
| `~/.agent_os/state.json` | **状态追踪**：记录“上一次打开的项目”路径。 |
| `./.agent/sessions.db` | **项目数据**：当前项目的对话历史、报错记录、Token 消耗统计。 |

---

## 🚀 交互模式 (Interactive REPL)

从 V1.1 版本开始，推荐使用交互式 REPL 模式。安装后使用 `aos` 或 `agent-os` 命令即可启动。

### 启动
```bash
# 默认启动 REPL
aos

# 或者显式启动
aos repl
```

---

## 🎮 交互与混合模型指南 (New in V1.2)

V1.2 版本引入了 **Hybrid Role Strategy (混合角色策略)**，允许你将不同的模型分配给不同的职责，以达到性能与成本的最佳平衡。

### 1. 核心概念：角色 (Roles)

系统包含两个核心角色：
- 🧠 **Planner (规划者)**: 负责分析错误、查阅资料、制定步骤。推荐逻辑强、Token 便宜的模型（如 GLM-4, DeepSeek-V3）。
- 👨‍💻 **Coder (编码者)**: 负责编写代码、生成 Patch。推荐代码能力强、上下文长的模型（如 DeepSeek-Coder, Claude-3.5）。

### 2. 状态栏解读
REPL 底部常亮显示当前配置：
```plaintext
[Planner: glm-4-plus | Coder: deepseek-v3]
```
这表示：思考用 GLM-4，写代码用 DeepSeek。

### 3. Slash Commands (常用指令)

| 指令 | 说明 | 示例 |
| --- | --- | --- |
| `/role <role> <model>` | **核心指令**：为指定角色绑定模型 | `/role planner glm-4-plus` |
| `/model <model>` | **快捷指令**：将 Planner 和 Coder 设为同一个模型 | `/model gpt-4o` |
| `/roles` | 查看当前角色分配详情 | `/roles` |
| `/models` | 列出所有可用模型及价格 ($/1M tokens) | `/models` |
| `/status` | 查看当前项目路径及 Session 状态 | `/status` |
| `/project [path]` | 切换到指定项目或查看当前项目信息 | `/project ~/my-app` |
| `/projects` | 列出所有历史项目及其最后活跃状态 | `/projects` |
| `/cost` | 查看分模型的 Token 消耗与预估费用 | `/cost` |
| `/clear` | 清空当前项目的记忆 (不影响其他项目) | `/clear` |
| `/config` | 查看加载的全局配置 | `/config` |
| `/help` | 显示帮助菜单 | `/help` |
| `/exit` | 退出程序 | `/exit` |

---

### 4. 最佳实践配置

- 💰 **极致性价比方案 (推荐)**
  ```bash
  /role planner deepseek-v3
  /role coder deepseek-coder
  ```
- 🚀 **土豪/攻坚方案 (解决疑难杂症)**
  ```bash
  /model gpt-4o
  ```
- 🛡️ **隐私/本地方案 (RTX 5090)**
  ```bash
  /model local-deepseek-coder-v2
  ```

### 5. 自动补全技巧
- 输入 `/role` 后按 **空格**，会自动弹出 `planner` / `coder` 选项。
- 选择角色后按 **空格**，会自动弹出 `config.yaml` 中配置好的所有模型列表。
- 支持模糊匹配，无需记忆全名。

---

### 3. 启动任务

```bash
# 场景：你有一个 docker build 失败的项目
python main.py start "修复当前目录中的 docker build 错误"

# 场景：恢复之前的会话
python main.py resume session_20231011_123456
```

---

## 🧠 模型配置与更换指南

系统实现了 `LLMClient` 抽象，**无缝切换云端/本地模型**只需修改 `config.yaml`。

### 1. 配置文件结构 (`config.yaml`)

```yaml
models:
  # 规划模型 (Planner)：负责思考、决策、查错。推荐高智商模型。
  planner:
    type: "openai"  # 或 "local"
    model_name: "deepseek-chat"
    api_key: "sk-xxxxxxxx" 
    api_base: "https://api.deepseek.com/v1" # 兼容 OpenAI 格式
    temperature: 0.1

  # 编码模型 (Coder)：负责写代码、改文件。推荐代码能力强的模型。
  coder:
    type: "local"
    path: "/models/deepseek-coder-33b.gguf"
    n_ctx: 16384
    n_gpu_layers: -1 # 针对高性能 GPU (如 5090) 全部卸载
```

### 2. 运作原理

* **Local 模式**: `ModelManager` 调用 `llama-cpp-python` 加载 GGUF 到显存。如果切换角色，会自动 `unload` 前一个模型释放显存。
* **OpenAI 模式**: 实例化 `OpenAICompatibleClient`，直接发 HTTP 请求。显存占用为 0，适合将 Planner 部署在云端。

---

## ✅ 已完成功能 (V1.0 Kernel)

### 核心运行时 (Runtime):
- [x] **Async Session**: 支持长时间运行任务的异步会话管理。
- [x] **PTY Terminal**: 真正的伪终端交互 (支持 top, 进度条, Ctrl+C)。
- [x] **Signal Handling**: 优雅处理中断与恢复 (Pause/Resume)。

### 大脑与记忆 (Brain & Memory):
- [x] **Model Manager**: 本地显存互斥管理 (自动 Load/Unload GGUF 模型)。
- [x] **History Memory**: 基于 SQLite 的错误记忆库，防止重复犯错。
- [x] **Output Observer**: 流式日志分析与错误分类器。

### 工具与安全 (Tools & Safety):
- [x] **Git Safety Net**: 修改代码前强制自动 Commit，支持一键回滚。
- [x] **File Editor**: 基于 Search & Replace 的精准代码修改。
- [x] **Docker Tool**: 流式构建日志监控与容器操作。
- [x] **Browser Tool**: 报错信息联网搜索与摘要。
- [x] **Completion Gate**: 循环检测与停滞检测，防止无效操作。
- [x] **Event System**: 15+ 种事件类型，全生命周期实时监控。
- [x] **Skill System**: 包含 GitClone, PythonScript 等 4 种预验证技能。

### 交互 (Interface):
- [x] **CLI**: start, resume, logs 命令行工具。
- [x] **Config System**: 基于 config.yaml 的灵活配置。

---

## 🛠️ 严谨工程化优化 Todo List (V2.0 Roadmap)

### 🔒 1. 安全边界 (Safety Guardrails) - **已实现 (V1.1)**
- [x] **实现 `SafetyPolicy` 类**：
  - **黑名单路径**: 禁止修改 `/etc`, `/usr`, `.git`, `config.yaml`。
  - **高危命令拦截**: 拦截 `rm -rf /`, `mkfs`, `dd` 等毁灭性命令。
  - **修改限流**: 单次 Step 最多修改 3 个文件，超过需人工审批。
- [ ] **沙箱化 (Sandbox)**: 让 Agent 只能在 Docker 容器内运行，挂载宿主机代码目录为 Volume。

### 🛑 2. 人类介入机制 (Human-in-the-Loop) - **中优先级**
- [ ] **引入 `WAITING_APPROVAL` 状态**: 当 `FileEditor` 准备修改文件时，展示 Diff 并等待确认。
- [ ] **紧急制动**: `Ctrl+D`触发 `Emergency Stop`（杀进程 + Git Reset）。

### 🧠 3. 记忆与上下文优化 (Context Optimization)
- [ ] **滑动窗口上下文**: 实现 `LogSummarizer`，压缩超长日志。
- [x] **跨 Session 记忆 (History Persistence)**: 建立全局 `knowledge.db`，记录历史项目的补坑经验。

### ☁️ 4. 云端与本地混合调度 (Hybrid Compute)
- [ ] **动态路由策略**: 简单任务 -> 本地模型；复杂推理 -> 云端模型。
- [x] **成本监控**: 自动记录 Token 消耗与费用 (/cost 命令)。

---

## 🔭 未来演进路线

1. **MCP (Model Context Protocol) 集成**: 使 Agent 能直接使用现成的 Tool (PostgreSQL, Slack, etc.)。
2. **Skill Library (技能库)**: 将成功的操作序列固化为可复用的 "Skill"。
3. **RL (Reinforcement Learning) 自进化**: 收集 DPO 数据集，针对项目风格微调专属模型。

---

## 🏆 验收汇总 (Final Delivery Summary)

所有 5 项核心工程化验证已通过：

| 测试项 | 状态 | 详细描述 |
| --- | --- | --- |
| **1. 完结门禁** | ✅ PASS | 循环检测（3次重复操作触发）、目标达成自动识别 |
| **2. 事件系统** | ✅ PASS | 发射 20 个事件，涵盖所有必选事件类型 |
| **3. 项目管理** | ✅ PASS | 支持 Init、历史项目检索、当前项目自动追踪 |
| **4. 历史溯源** | ✅ PASS | SQLite 持久化存储、历史记录上下文自动构建 |
| **5. 费用分析** | ✅ PASS | 实时货币计算 (测试场景消耗: $0.001570) |
| **6. GLM 集成** | ✅ PASS | 真实 API 调用，2 步内完成指定任务 |
| **7. 自动克隆** | ✅ PASS | GitClone 技能成功克隆 octocat/Hello-World |

---
### 核心演进

- **完结门禁 (agent_core/completion.py)**: 防止 Agent 陷入死循环或无意义重试。
- **事件系统 (agent_core/events.py)**: 实时发射 AGENT_START, PLANNER_*, EXECUTOR_* 等事件。
- **技能库 (agent_core/skills.py)**: 包含 GitClone, PythonScript 等预验证技能。
- **费用监控**: `/cost` 指令支持多模型分摊计算。

---

## 📜 License

MIT License

---

## 📊 功能对比 (Comparison)

| 功能维度 | 功能点 | DebugFlow (Agent OS) | Claude Code (官方) | OpenCode / Interpreter | Oh-My-OpenCode |
| --- | --- | --- | --- | --- | --- |
| **核心定位** | 主要用途 | **深度工程调试 & 修复** | 通用代码辅助 & 问答 | 通用自动化 & 脚本执行 | 极客定制版自动化 |
| **算力模式** | 模型支持 | **本地(5090) + 云端混合** | 仅限 Anthropic 云端 | 任意 (本地/云端) | 任意 (本地/云端) |
| **执行环境** | 终端交互 (PTY) | **✅ (核心强项)** | ✅ | ⚠️ (部分 subprocess) | ⚠️ |
| | 状态保持 (Session) | **✅ (SQLite持久化)** | ❌ (退出即忘) | ⚠️ (运行时内存) | ⚠️ |
| | 长任务中断恢复 | **✅ (Pause/Resume)** | ❌ | ❌ | ❌ |
| | 进程级控制 | **✅ (Ctrl+C 优雅暂停)** | ⚠️ | ❌ (容易卡死) | ⚠️ |
| **安全性** | Git 自动快照 | **✅ (强制 Checkpoint)** | ❌ | ❌ (裸奔) | ❌ |
| | 沙箱/权限控制 | ⚠️ (Phase 7 Todo) | ⚠️ (云端环境) | ❌ (Root 裸奔) | ❌ |
| | 修改确认 | ⚠️ (Todo) | ✅ (每次确认) | ✅ (可选) | ✅ |
| **智能特性** | 错误记忆 (Memory) | **✅ (防重复犯错)** | ❌ | ❌ | ❌ |
| | 主动查错 (Observer) | **✅ (流式分析)** | ⚠️ | ❌ (靠 LLM 自己看) | ❌ |
| | 联网搜索 | **✅ (BrowserTool)** | ❌ (知识截止) | ✅ | ✅ |
| **交互体验** | 交互式 REPL | **✅ (Phase 8)** | ✅ (非常丝滑) | ✅ | ✅ |
| | Slash Commands | **✅ (/model, /cost)** | ✅ (/bug, /review) | ✅ (/save) | ✅ |
| | UI 美观度 | ⚠️ (基于 Rich) | **✅ (极致打磨)** | ⚠️ | ⚠️ |
| **生态** | MCP 协议支持 | 🔧 (架构支持, 待加) | ✅ (原生支持) | ⚠️ (试验中) | ⚠️ |
| | 多模型切换 | **✅ (GGUF/API 秒切)** | ❌ (仅 Claude) | ✅ | ✅ |

---

> **设计目标：让 Agent 像一个可靠的工程师，而不是话多的聊天机器人。**

