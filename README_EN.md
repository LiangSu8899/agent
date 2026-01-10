# Agent Debug OS

<p align="center">
  <a href="README.md">中文</a> | <a href="README_EN.md">English</a>
</p>

> A Debug-First Agent Runtime for Real-World Engineering Tasks

---

## 📌 Project Overview

**Agent Debug OS** is a **debug-first agent runtime** designed for real engineering workflows, not chat-based demos.

It focuses on:

- Long-running tasks (Docker builds, CI pipelines, compilation)
- Interruptible and resumable execution
- Automatic error detection and recovery attempts
- Persistent session state and failure memory
- Flexible usage of local or API-based LLMs

Think of it as an **Operating System for Debugging**, not a chatbot.

---

## 🧱 Core Design Philosophy

### 1. Session First

- Every task runs inside a **Session**
- Sessions have persistent state stored in SQLite
- Lifecycle:

```
Created → Running → Paused → Completed / Failed
```

### 2. Real Terminal (PTY-based)

- Uses a real **Pseudo-Terminal (PTY)** instead of subprocess wrappers
- Supports attach / detach
- Suitable for Docker, compilers, and interactive commands

### 3. Debug Loop, Not Prompt Loop

- Observe stdout / stderr
- Detect and classify errors
- Query failure history to avoid repeating the same fixes
- Decide the next corrective action

### 4. Safety by Design

- All file changes are checkpointed with Git
- Diff preview before applying changes
- Every failure is traceable, reviewable, and reversible

---

## 📁 Project Structure

```
agent/
├── agent_core/          # Core runtime (Session / Terminal / Agent)
│   ├── session.py
│   ├── terminal.py
│   ├── models.py
│   ├── memory.py
│   └── agent.py
│
├── agent_tools/         # Tools (File / Git / Docker / Browser)
│   ├── file_editor.py
│   ├── git_handler.py
│   ├── docker_tool.py
│   └── browser_tool.py
│
├── tests/               # Phase-based verification tests
├── sandbox_test/        # File/code modification sandbox
├── config.yaml          # Agent & model configuration
├── sessions.db          # Session state database
└── main.py              # Entry point
```

---

## 🚀 Quick Start

### Step 1: Clone the repository

```
git clone https://github.com/LiangSu8899/agent.git
cd agent
```

### Step 2: Install dependencies

```
pip install -r requirements.txt
```

If `requirements.txt` is not available:

```
pip install openai transformers tiktoken pyyaml
```

### Step 3: Configure the model

Edit `config.yaml`.

#### API-based model

```
model:
  provider: openai
  name: gpt-4o-mini
```

Set environment variable:

```
export OPENAI_API_KEY="your_api_key"
```

#### Local model (llama.cpp / GGUF)

```
model:
  provider: local
  backend: llama.cpp
  model_path: ./models/coder-7b.gguf
```

---

## ▶️ Running the Agent

Start the agent runtime:

```
python main.py
```

### Programmatic example

```
from agent_core.session import Session

session = Session.create(
    command="for i in {1..5}; do echo $i; sleep 1; done"
)

session.start_async()
```

Supported features:

- attach / detach
- pause / resume
- persistent logs

---

## 🧪 Testing

Run phase-based verification tests:

```
python tests/phase1_verify.py
python tests/phase2_verify.py
```

| Phase   | Capability                          |
|--------|--------------------------------------|
| Phase 1 | Session & PTY runtime                |
| Phase 2 | Local model management               |
| Phase 3 | Debug loop & failure memory          |
| Phase 4 | Safe file modification & rollback    |
| Phase 5 | Docker & browser tools               |

---

## 🧠 Use Cases

- Docker build and CI debugging
- Dependency and environment issue fixing
- Local LLM–assisted engineering workflows
- Agent system research and experimentation

---

## ⚠️ Project Status

- Active development
- Focused on architecture validation and engineering correctness
- API stability is not guaranteed yet

Issues and pull requests are welcome.

---

## 📜 License

MIT License

---

If you are tired of agents that can talk but cannot debug —

**this project is built for you.**