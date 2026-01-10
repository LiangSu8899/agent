# Agent Debug OS (Agent OS V1.0)

<p align="center">
  <a href="README_EN.md">English</a> | <a href="README.md">中文</a>
</p>

> **A Debug-First Agent Runtime, and more importantly, an "Engineering-Grade Agent OS Prototype".**  
> A Engineering-Grade Agent OS Prototype for Real-World Debugging.

---

## 📌 System Architecture

Agent Debug OS is not a linear LLM Q&A system, but a **closed-loop control system based on a State Machine**.

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

## 🧱 Core Modules

| Module | Responsibility | Key Features |
| --- | --- | --- |
| **Session** | Task runtime container | Async, PTY support, Pause/Resume, Log persistence |
| **Orchestrator** | Commander-in-Chief | Orchestrates Agent & Session, handles user signals (Ctrl+C), lifecycle management |
| **ModelManager** | Compute Scheduler | VRAM mutual exclusion (Auto Unload), Token counting, multi-backend (Local/API) |
| **HistoryMemory** | Experience Base | Records `(Command, Error, Result)`, prevents Agent from infinite loops |
| **GitHandler** | Safety Net | Mandatory Git commits before any file modification, `reset --hard` capability |
| **Observer** | Perception | Real-time streaming log analysis, regex-based error matching |

---

## 🚀 Quick Start

### 1. Environment Preparation

```bash
# 1. Clone the repo
git clone https://github.com/LiangSu8899/agent.git agent-os
cd agent-os

# 2. Create virtual environment (Python 3.10+ recommended)
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
# Core dependencies: llama-cpp-python, duckduckgo-search, gitpython, docker, tiktoken, openai
```

### 2. Initial Configuration

`config.yaml` is generated automatically on first run, but manual configuration is recommended.

```bash
# View help and run once to generate config
python main.py --help
vim config.yaml
```

### 3. Start a Task

```bash
# Scenario: Fixing a broken Docker build
python main.py start "Fix the docker build error in current directory"

# Scenario: Resume a previous session
python main.py resume session_20231011_123456
```

---

## 🧠 Model Configuration Guide

The system implements an `LLMClient` abstraction, allowing **seamless switching between Cloud and Local models** via `config.yaml`.

### 1. Configuration Structure (`config.yaml`)

```yaml
models:
  # Planner: Responsible for thinking, decision making, and error detection.
  planner:
    type: "openai"  # or "local"
    model_name: "deepseek-chat"
    api_key: "sk-xxxxxxxx" 
    api_base: "https://api.deepseek.com/v1" # OpenAI-compatible
    temperature: 0.1

  # Coder: Responsible for writing code and modifying files.
  coder:
    type: "local"
    path: "/models/deepseek-coder-33b.gguf"
    n_ctx: 16384
    n_gpu_layers: -1 # Offload all to GPU (e.g., RTX 5090)
```

### 2. How it Works

* **Local Mode**: `ModelManager` uses `llama-cpp-python` to load GGUF into VRAM. It automatically `unloads` the previous model when switching roles to free up VRAM.
* **OpenAI Mode**: Instantiates `OpenAICompatibleClient` for direct HTTP requests. Zero VRAM usage, ideal for offloading the Planner to the cloud.

---

## 🛠️ Engineering Optimization Todo List (V2.0 Roadmap)

### 🔒 1. Safety Guardrails - **High Priority**
- [ ] **Implement `SafetyPolicy` Class**:
  - **Blacklisted Paths**: Prevent modification of `/etc`, `/usr`, `.git`, `config.yaml`.
  - **Dangerous Command Interception**: Block `rm -rf /`, `mkfs`, `dd`, etc.
  - **Rate Limiting**: Limit the number of file modifications per step.
- [ ] **Sandboxing**: Run the Agent inside a Docker container, mounting the host code as a volume.

### 🛑 2. Human-in-the-Loop - **Medium Priority**
- [ ] **Introduce `WAITING_APPROVAL` State**: Pause and show Diffs before applying file changes.
- [ ] **Emergency Stop**: `Ctrl+D` triggers an immediate stop (kill process + Git Reset).

### 🧠 3. Context Optimization
- [ ] **Sliding Window Context**: Implement `LogSummarizer` to compress long log outputs.
- [ ] **Cross-Session Memory (RAG)**: Establish a global `knowledge.db` to reuse debugging experiences across projects.

### ☁️ 4. Hybrid Compute
- [ ] **Dynamic Routing**: Use local models for simple tasks; cloud models for complex reasoning.
- [ ] **Cost Monitoring**: Track token usage and API costs.

---

## 🔭 Future Evolution

1. **MCP (Model Context Protocol) Integration**: Allow the Agent to use community tools (PostgreSQL, Slack, etc.).
2. **Skill Library**: Persist successful operation sequences as reusable "Skills".
3. **RL (Reinforcement Learning) Self-Evolution**: Collect DPO datasets to fine-tune project-specific models.

---

## 📜 License

MIT License

---

> **Design Goal: Make the Agent a reliable engineer, not a talkative chatbot.**