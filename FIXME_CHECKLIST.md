# 🔧 缺陷修复清单

## 📋 总体情况
- **测试通过率**: 80% (12/15)
- **发现的问题**: 3 个 P0 优先级的中等严重缺陷
- **修复预期**: 100% (预计本周内完成)
- **总工作量**: 5-10 小时

---

## 问题 #1: HistoryMemory - LLM 上下文格式缺陷

### 📌 基本信息
- **模块**: HistoryMemory (错误记忆)
- **文件**: `agent_core/memory/history.py`
- **方法**: `get_context_for_prompt()`
- **严重程度**: MEDIUM
- **修复难度**: LOW
- **预计工作量**: 1-2 小时

### 🔴 问题描述
生成的 LLM 上下文中缺少"Failed Commands"部分，导致 LLM 不会收到失败命令的完整警告信息。

### ❌ 失败的测试
```
Test: history_context_generation [FAILED]
Error: Context should have failure section
Expected: 包含"Failed Commands"标记
Actual: 标记不存在或格式不正确
```

### 💡 修复方案
在 `get_context_for_prompt()` 方法中添加显式的失败命令部分：

```python
def get_context_for_prompt(self, max_entries: int = 5) -> str:
    # 现有代码...

    # 获取失败的命令
    failed_commands = self.get_failed_commands()

    # 添加失败命令部分
    if failed_commands:
        context += "\n⚠️ Failed Commands (DO NOT RETRY):\n"
        for cmd in failed_commands:
            context += f"  - {cmd}\n"

    return context
```

### ✅ 验证方式
```bash
python test_core_modules.py
# 期望结果: history_context_generation 应该 PASS
```

---

## 问题 #2: SessionManager - 状态转换逻辑缺陷

### 📌 基本信息
- **模块**: SessionManager (会话管理)
- **文件**: `agent_core/session.py`
- **方法**: `start_session()` 和 `Session._monitor_process()`
- **严重程度**: MEDIUM
- **修复难度**: MEDIUM
- **预计工作量**: 2-4 小时

### 🔴 问题描述
调用 `start_session()` 后，会话状态直接跳到 COMPLETED，而不是正确地转换为 RUNNING。

### ❌ 失败的测试
```
Test: session_lifecycle [FAILED]
Error: Should be RUNNING, got COMPLETED
Expected: PENDING → RUNNING → COMPLETED
Actual: PENDING → COMPLETED (跳过了 RUNNING)
```

### 💡 问题根源分析
1. `start_session()` 方法可能没有正确设置状态为 RUNNING
2. `Session.start()` 可能立即启动并完成进程
3. `Session._monitor_process()` 可能立即设置为完成

### 🔧 调试步骤

1. **检查 start_session() 实现**:
```python
def start_session(self, session_id: str) -> None:
    session = self._sessions.get(session_id)
    if session:
        session.start()  # 这应该设置为 RUNNING
        # 确保数据库也更新为 RUNNING
        self._update_db(session)
```

2. **检查 Session.start() 实现**:
```python
def start(self) -> None:
    self.status = SessionStatus.RUNNING
    # 启动 PTY 终端但不立即完成
    self._terminal.start()
```

3. **检查 _monitor_process() 逻辑**:
```python
def _monitor_process(self) -> None:
    # 这个函数应该在后台线程中运行
    # 不应该立即设置状态为 COMPLETED
    while True:
        if self._terminal.is_closed():
            self.status = SessionStatus.COMPLETED
            break
```

### ✅ 验证方式
```bash
python test_core_modules.py
# 期望结果: session_lifecycle 应该 PASS
```

---

## 问题 #3: CompletionGate - 停滞检测失效

### 📌 基本信息
- **模块**: CompletionGate (完成门禁)
- **文件**: `agent_core/completion.py`
- **方法**: `check_completion()`
- **严重程度**: MEDIUM
- **修复难度**: MEDIUM
- **预计工作量**: 2-4 小时

### 🔴 问题描述
CompletionGate 无法检测任务停滞（无状态变化的重复操作）。

### ❌ 失败的测试
```
Test: completion_stall_detection [FAILED]
Error: Should detect stalled task
Expected: 在6次相同命令执行后检测到停滞
Actual: 从未检测到停滞
```

### 💡 问题根源分析
可能的原因：
1. `state_hash` 计算不准确
2. `stall_count` 递增逻辑有缺陷
3. 停滞计数被不当重置

### 🔧 调试步骤

1. **验证 state_hash 计算**:
```python
def take_snapshot(self) -> StateSnapshot:
    # 确保快照包含足够的信息来检测停滞
    # 应该包括：
    # - 文件修改时间
    # - 目录内容变化
    # - 命令执行的效果
    return StateSnapshot(...)
```

2. **检查 stall_count 逻辑**:
```python
def check_completion(self, command: str, output: str, exit_code: int, thought: str = ""):
    # 应该跟踪：
    # - 命令哈希是否重复
    # - 状态是否有变化
    # - 重复无变化时 stall_count 应该递增

    if same_command_hash and same_state_hash:
        self.stall_count += 1  # 这里可能有问题
    else:
        self.stall_count = 0  # 重置

    if self.stall_count >= self.max_stall_count:
        return CompletionStatus.STALLED
```

3. **添加调试日志**:
```python
# 在 check_completion() 中添加详细日志
print(f"DEBUG: command={command[:30]}")
print(f"DEBUG: state_hash={self._current_state_hash}")
print(f"DEBUG: stall_count={self.stall_count}")
print(f"DEBUG: max_stall_count={self.max_stall_count}")
```

### ✅ 验证方式
```bash
python test_core_modules.py
# 期望结果: completion_stall_detection 应该 PASS
```

---

## 📋 修复检查清单

### 对于每个问题，完成以下步骤：

#### HistoryMemory 问题:
- [ ] 打开 `agent_core/memory/history.py`
- [ ] 找到 `get_context_for_prompt()` 方法
- [ ] 添加失败命令部分
- [ ] 运行测试: `python test_core_modules.py`
- [ ] 验证 `history_context_generation` 测试通过
- [ ] 提交更改

#### SessionManager 问题:
- [ ] 打开 `agent_core/session.py`
- [ ] 审查 `start_session()` 实现
- [ ] 审查 `Session.start()` 实现
- [ ] 审查 `Session._monitor_process()` 实现
- [ ] 添加调试日志
- [ ] 运行测试: `python test_core_modules.py`
- [ ] 验证 `session_lifecycle` 测试通过
- [ ] 提交更改

#### CompletionGate 问题:
- [ ] 打开 `agent_core/completion.py`
- [ ] 审查 `take_snapshot()` 实现
- [ ] 审查 `check_completion()` 中的 stall_count 逻辑
- [ ] 添加详细的调试日志
- [ ] 运行测试: `python test_core_modules.py`
- [ ] 验证 `completion_stall_detection` 测试通过
- [ ] 提交更改

### 最终验证:
- [ ] 所有 15 个测试都通过 (100%)
- [ ] `python test_core_modules.py` 输出显示 "Pass Rate: 100.0%"
- [ ] 所有更改已提交到 git

---

## 🚀 修复时间表

| 任务 | 预计时间 | 优先级 |
|------|---------|--------|
| HistoryMemory 修复 | 1-2h | P0 |
| SessionManager 修复 | 2-4h | P0 |
| CompletionGate 修复 | 2-4h | P0 |
| 测试和验证 | 1h | P0 |
| **总计** | **5-10h** | |

**建议时间表**:
- 今天: 完成 HistoryMemory 修复 (1-2h)
- 明天: 完成 SessionManager 修复 (2-4h)
- 后天: 完成 CompletionGate 修复 (2-4h)
- 周末: 最终测试和验证

---

## 📞 参考资源

- **测试代码**: `test_core_modules.py`
- **测试报告**: `test_results/ROBUSTNESS_REPORT.md`
- **快速指南**: `test_results/QUICK_START.md`
- **JSON 数据**: `test_results/robustness_report.json`

---

**最后更新**: 2026-01-11
**预期完成**: 本周内
**目标通过率**: 100% (15/15 测试)
