# Agent Debug OS (Agent OS V1.0)

<p align="center">
  <a href="README_EN.md">English</a> | <a href="README.md">中文</a>
</p>

> **一个面向真实工程调试场景的 Agent Runtime，更是一个“工程化的 Agent OS 雏形”。**  
> A Engineering-Grade Agent OS Prototype for Real-World Debugging.

---

## 📌 系统架构 (System Architecture)

Agent Debug OS 不是线性的 LLM 问答，而是一个**基于状态机（State Machine）的闭环控制系统**。

```mermaid
graph TD
    User[👨‍💻 User] -->|CLI Commands| Main[Entrypoint (main.py)]
    Main -->|Init| Orch[Orchestrator]
    
    subgraph "Agent OS Runtime"
        Orch -->|Manage| Session[Session (PTY/Process)]
        Orch -->|Manage| Agent[Debug Agent]
        
        Session <-->|Stdin/Stdout| Terminal[💻 Real Terminal]
        
        Agent -->|Observe| Observer[Output Observer]
        Observer -->|Parse Logs| Terminal
        
        Agent -->|Think| Brain[Model Manager]
        Brain -->|Load/Unload| LLM[Local/Cloud Models]
        
        Agent -->|Recall| Memory[History Memory (SQLite)]
        
        Agent -->|Act| Tools[Toolbox]
    end
    
    subgraph "Toolbox (The Hands)"
        Tools --> Git[Git Handler]
        Tools --> File[File Editor]
        Tools --> Docker[Docker Tool]
        Tools --> Browser[Browser Tool]
    end
    
    Git -->|Safety Checkpoint| FileSystem
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

# 3. 安装依赖
pip install -r requirements.txt
# 核心依赖：llama-cpp-python, duckduckgo-search, gitpython, docker, tiktoken, openai
```

### 2. 初始化配置

首次运行会自动生成 `config.yaml`，建议手动配置模型路径。

```bash
# 查看帮助并运行一次生成配置
python main.py --help
vim config.yaml
```

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

## 🛠️ 严谨工程化优化 Todo List (V2.0 Roadmap)

### 🔒 1. 安全边界 (Safety Guardrails) - **高优先级**
- [ ] **实现 `SafetyPolicy` 类**：
  - **黑名单路径**: 禁止修改 `/etc`, `/usr`, `.git`, `config.yaml`。
  - **高危命令拦截**: 拦截 `rm -rf /`, `mkfs`, `dd` 等毁灭性命令。
  - **修改限流**: 单次 Step 最多修改 3 个文件，超过需人工审批。
- [ ] **沙箱化 (Sandbox)**: 让 Agent 只能在 Docker 容器内运行，挂载宿主机代码目录为 Volume。

### 🛑 2. 人类介入机制 (Human-in-the-Loop) - **中优先级**
- [ ] **引入 `WAITING_APPROVAL` 状态**: 当 `FileEditor` 准备修改文件时，展示 Diff 并等待确认。
- [ ] **紧急制动**: `Ctrl+D` 触发 `Emergency Stop`（杀进程 + Git Reset）。

### 🧠 3. 记忆与上下文优化 (Context Optimization)
- [ ] **滑动窗口上下文**: 实现 `LogSummarizer`，压缩超长日志。
- [ ] **跨 Session 记忆 (RAG)**: 建立全局 `knowledge.db`，记录历史项目的补坑经验。

### ☁️ 4. 云端与本地混合调度 (Hybrid Compute)
- [ ] **动态路由策略**: 简单任务 -> 本地模型；复杂推理 -> 云端模型。
- [ ] **成本监控**: 记录 Token 消耗与费用。

---

## 🔭 未来演进路线

1. **MCP (Model Context Protocol) 集成**: 使 Agent 能直接使用现成的 Tool (PostgreSQL, Slack, etc.)。
2. **Skill Library (技能库)**: 将成功的操作序列固化为可复用的 "Skill"。
3. **RL (Reinforcement Learning) 自进化**: 收集 DPO 数据集，针对项目风格微调专属模型。

---

## 📜 License

MIT License

---

> **设计目标：让 Agent 像一个可靠的工程师，而不是话多的聊天机器人。**

