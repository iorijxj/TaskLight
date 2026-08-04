# TaskLight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Windows 桌面红绿灯，聚合所有 Claude Code 会话（CLI + VS Code 扩展）的忙闲状态，红=繁忙 / 橙=后台任务运行中 / 绿=待机。

**Architecture:** Claude Code hooks 把每会话状态写成幂等文件快照到 `~\.claude\tasklight\`；GUI 每 400ms 扫目录聚合，按 `waiting > busy > 后台标记 > 进程探测` 短路判定灯色。后台 Bash 无完成事件，靠「进程创建时间晚于该会话 `bg_since`」识别，从而与常驻 MCP 进程区分开。

**Tech Stack:** Python 3.13.2 / tkinter（悬浮窗）/ pystray + Pillow（托盘）/ ctypes Win32 API（进程探测）/ pytest

设计依据：`docs/superpowers/specs/2026-08-04-tasklight-design.md`

## Global Constraints

- 平台 Windows 11，Python 3.13.2（已确认自带 tkinter 8.6）
- `hooks/` 与 `tasklight/store.py`、`tasklight/winproc.py` **只能用标准库**（hook 进程冷启动要快）；`pystray` / `Pillow` 仅限 `tray.py`
- hook 脚本**任何情况下都必须 `exit 0`**，顶层 try/except 吞掉一切异常
- 所有落盘 id 先过 `sanitize_id()`（`[^A-Za-z0-9_-] → _`）
- 状态槽位根目录 `~\.claude\tasklight\`，测试一律用 `tmp_path` 注入，**禁止让测试碰真实目录**
- 函数 <50 行、文件 <800 行、嵌套 <4 层
- UI 文案与注释用中文；不写冗余注释
- `E:\Github\TaskLight` 目前**不是 git 仓库**。若用户批准 `git init`，则执行各任务的 Commit 步骤；否则跳过所有 Commit 步骤，其余照做

---

## File Structure

| 文件 | 职责 |
|---|---|
| `tasklight/state.py` | 灯色判定纯函数 + `Light` / `Slot` 类型。零 I/O |
| `tasklight/store.py` | 槽位目录读写、标记文件增删、陈旧与孤儿清理 |
| `tasklight/winproc.py` | ctypes 封装：进程表快照、进程创建时间、父链找 `claude.exe` |
| `tasklight/probe.py` | 后台活动判定：后代枚举 + 创建时间过滤。进程表与时间取值均可注入 |
| `tasklight/widget.py` | tkinter 置顶悬浮窗 |
| `tasklight/tray.py` | pystray 托盘图标 |
| `main.py` | 组装：400ms tick、懒探测节流、widget + tray 生命周期 |
| `hooks/tasklight_hook.py` | 唯一 hook 脚本，按 `hook_event_name` 分派 |
| `install_hooks.py` | 幂等合并 hooks 进 `~\.claude\settings.json` |

依赖方向单一：`state` ← `store` / `probe` ← `main`；`winproc` 被 `probe` 与 hook 共用。`state.py` 不 import 任何本项目模块。

---

## Task 1: 项目骨架与假设验证

先拿真实 payload 再写代码 —— spec 第 6 节有三条未实测的假设，猜错会让后面全部返工。

**Files:**
- Create: `pyproject.toml`
- Create: `tasklight/__init__.py`
- Create: `tests/__init__.py`
- Create: `hooks/dump_payload.py`
- Create: `docs/hook-payload-findings.md`

**Interfaces:**
- Consumes: 无
- Produces: `docs/hook-payload-findings.md` —— 后续任务据此确认 `SubagentStart.session_id` 归属、`PostToolUse` 的 `run_in_background` 字段路径、VS Code 扩展是否触发 hooks

- [ ] **Step 1: 建项目骨架**

`pyproject.toml`：

```toml
[project]
name = "tasklight"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["pystray>=0.19", "Pillow>=10"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`tasklight/__init__.py` 与 `tests/__init__.py` 均为空文件。

- [ ] **Step 2: 装依赖**

Run: `python -m pip install -e ".[dev]"`
Expected: 成功装上 pystray、Pillow、pytest

- [ ] **Step 3: 写临时 dump hook**

`hooks/dump_payload.py`：

```python
"""临时诊断脚本：把每次 hook 的原始 payload 追加到 dump.jsonl。验证完即删。"""
import json
import os
import sys
import time
from pathlib import Path

OUT = Path.home() / ".claude" / "tasklight" / "dump.jsonl"


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {"_unparsed": raw[:2000]}
    payload["_received_at"] = time.time()
    payload["_hook_pid"] = os.getpid()
    payload["_hook_ppid"] = os.getppid()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
```

- [ ] **Step 4: 临时挂上全部待验证事件**

手工把下面这段**合并**进 `%USERPROFILE%\.claude\settings.json` 的 `hooks` 键（保留已有的 `verify-write-fresh` 条目）。这是临时配置，Step 7 会摘掉。

```json
{
  "SubagentStart": [{"hooks": [{"type": "command", "command": "python \"E:/Github/TaskLight/hooks/dump_payload.py\"", "timeout": 10}]}],
  "SubagentStop":  [{"hooks": [{"type": "command", "command": "python \"E:/Github/TaskLight/hooks/dump_payload.py\"", "timeout": 10}]}],
  "PostToolUse":   [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python \"E:/Github/TaskLight/hooks/dump_payload.py\"", "timeout": 10}]}],
  "SessionStart":  [{"hooks": [{"type": "command", "command": "python \"E:/Github/TaskLight/hooks/dump_payload.py\"", "timeout": 10}]}],
  "Notification":  [{"matcher": "permission_prompt", "hooks": [{"type": "command", "command": "python \"E:/Github/TaskLight/hooks/dump_payload.py\"", "timeout": 10}]}]
}
```

- [ ] **Step 5: 跑一遍全场景采样**

重启 Claude Code（hooks 在启动时加载），然后依次做：

1. 在 CLI 会话里派一个子 Agent（任意只读探索任务）
2. 起一个后台 Bash：`Bash(command="ping -n 30 127.0.0.1", run_in_background=true)`
3. 触发一次权限确认弹窗
4. **在 VS Code 里开一个 Claude Code 会话，随便发一句话**

- [ ] **Step 6: 记录结论**

Run: `python -c "import json,pathlib; [print(json.dumps(json.loads(l), ensure_ascii=False, indent=1)) for l in pathlib.Path.home().joinpath('.claude/tasklight/dump.jsonl').read_text(encoding='utf-8').splitlines()]"`

把答案写进 `docs/hook-payload-findings.md`，必须明确回答四问：

1. `SubagentStart` / `SubagentStop` 的 `session_id` 与主会话的 `SessionStart.session_id` **是否相同**？（若不同，Task 3 的 `agents\<session_id>\` 归属键要换成主会话 id 的来源字段，并在此记录该字段名）
2. `PostToolUse` 里后台 Bash 的标志位完整路径是否为 `tool_input.run_in_background`？`tool_response` 中是否含 PID 或 shell id？
3. VS Code 扩展会话是否产生了 dump 记录？其 `_hook_ppid` 对应的进程名是什么？
4. `_hook_ppid` 是否直接就是 `claude.exe`？（若是，Task 4 的父链查找可简化为一层，但仍保留循环以防万一）

- [ ] **Step 7: 摘掉临时 hook**

从 `%USERPROFILE%\.claude\settings.json` 移除 Step 4 加的五个条目，恢复到只剩 `verify-write-fresh`。删除 `~\.claude\tasklight\dump.jsonl`。

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml tasklight/__init__.py tests/__init__.py hooks/dump_payload.py docs/hook-payload-findings.md
git commit -m "chore: 项目骨架与 hook payload 实测结论"
```

---

## Task 2: state.py 灯色判定

纯逻辑，零 I/O，先钉死。

**Files:**
- Create: `tasklight/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `Light` 枚举：`RED_BLINK` / `RED` / `ORANGE` / `GREEN`
  - 常量 `SESSION_IDLE = "idle"`、`SESSION_BUSY = "busy"`、`SESSION_WAITING = "waiting"`
  - `Slot` 冻结数据类：`session_id: str`、`state: str`、`cwd: str`、`bg_since: float | None`、`claude_pid: int | None`、`updated_at: float`、`pending_agents: int`、`pending_tasks: int`
  - `resolve_without_probe(slots: list[Slot]) -> Light | None` —— 返回 `None` 表示需要探测才能定夺
  - `resolve(slots: list[Slot], background_active: bool) -> Light`
  - `summarize(slots: list[Slot], light: Light) -> str` —— 托盘 tooltip 文案

- [ ] **Step 1: 写失败测试**

`tests/test_state.py`：

```python
from tasklight.state import (
    Light,
    Slot,
    SESSION_BUSY,
    SESSION_IDLE,
    SESSION_WAITING,
    resolve,
    resolve_without_probe,
    summarize,
)


def slot(state=SESSION_IDLE, agents=0, tasks=0, bg_since=None):
    return Slot(
        session_id="s1",
        state=state,
        cwd="E:\\proj",
        bg_since=bg_since,
        claude_pid=None,
        updated_at=0.0,
        pending_agents=agents,
        pending_tasks=tasks,
    )


def test_waiting_压过_busy():
    slots = [slot(SESSION_BUSY), slot(SESSION_WAITING)]
    assert resolve_without_probe(slots) is Light.RED_BLINK


def test_busy_压过_未完成子agent():
    slots = [slot(SESSION_IDLE, agents=3), slot(SESSION_BUSY)]
    assert resolve_without_probe(slots) is Light.RED


def test_前台全停但有未完成子agent时为橙():
    assert resolve_without_probe([slot(SESSION_IDLE, agents=1)]) is Light.ORANGE


def test_前台全停但有未完成task时为橙():
    assert resolve_without_probe([slot(SESSION_IDLE, tasks=1)]) is Light.ORANGE


def test_全部空闲时需要探测才能定夺():
    assert resolve_without_probe([slot(SESSION_IDLE)]) is None


def test_无任何会话时需要探测才能定夺():
    assert resolve_without_probe([]) is None


def test_探测命中为橙():
    assert resolve([slot(SESSION_IDLE)], background_active=True) is Light.ORANGE


def test_探测未命中为绿():
    assert resolve([slot(SESSION_IDLE)], background_active=False) is Light.GREEN


def test_探测结果不影响已定夺的灯色():
    assert resolve([slot(SESSION_BUSY)], background_active=True) is Light.RED


def test_摘要含会话数与后台数():
    slots = [slot(SESSION_BUSY), slot(SESSION_IDLE, agents=2)]
    text = summarize(slots, Light.RED)
    assert "忙碌" in text and "1 会话" in text and "后台 2" in text


def test_待机摘要不带多余计数():
    assert summarize([slot(SESSION_IDLE)], Light.GREEN) == "待机"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'tasklight.state'`

- [ ] **Step 3: 实现**

`tasklight/state.py`：

```python
"""灯色判定。纯函数，不做任何 I/O。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

SESSION_IDLE = "idle"
SESSION_BUSY = "busy"
SESSION_WAITING = "waiting"


class Light(Enum):
    RED_BLINK = "red_blink"
    RED = "red"
    ORANGE = "orange"
    GREEN = "green"


LIGHT_LABELS = {
    Light.RED_BLINK: "等待确认",
    Light.RED: "忙碌",
    Light.ORANGE: "后台运行",
    Light.GREEN: "待机",
}


@dataclass(frozen=True)
class Slot:
    session_id: str
    state: str
    cwd: str
    bg_since: float | None
    claude_pid: int | None
    updated_at: float
    pending_agents: int
    pending_tasks: int


def resolve_without_probe(slots: list[Slot]) -> Light | None:
    """前三级判定。返回 None 表示要靠进程探测才能在橙与绿之间定夺。"""
    if any(s.state == SESSION_WAITING for s in slots):
        return Light.RED_BLINK
    if any(s.state == SESSION_BUSY for s in slots):
        return Light.RED
    if any(s.pending_agents or s.pending_tasks for s in slots):
        return Light.ORANGE
    return None


def resolve(slots: list[Slot], background_active: bool) -> Light:
    early = resolve_without_probe(slots)
    if early is not None:
        return early
    return Light.ORANGE if background_active else Light.GREEN


def summarize(slots: list[Slot], light: Light) -> str:
    parts = [LIGHT_LABELS[light]]
    active = sum(1 for s in slots if s.state in (SESSION_BUSY, SESSION_WAITING))
    pending = sum(s.pending_agents + s.pending_tasks for s in slots)
    if active:
        parts.append(f"{active} 会话")
    if pending:
        parts.append(f"后台 {pending}")
    return " · ".join(parts)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_state.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add tasklight/state.py tests/test_state.py
git commit -m "feat: 灯色判定纯逻辑"
```

---

## Task 3: store.py 槽位存储

**Files:**
- Create: `tasklight/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `tasklight.state.Slot`
- Produces（`root: Path` 一律显式传入，便于测试注入 `tmp_path`）：
  - `DEFAULT_ROOT: Path` = `Path.home() / ".claude" / "tasklight"`
  - `STALE_SECONDS: int` = `4 * 3600`
  - `sanitize_id(raw) -> str`
  - `write_slot(root, session_id, **fields) -> None` —— 与现有内容合并后原子覆写，自动刷新 `updated_at`
  - `mark_add(root, kind, session_id, item_id) -> None`，`kind` ∈ `"agents" | "tasks"`
  - `mark_remove(root, kind, session_id, item_id) -> None`
  - `drop_session(root, session_id) -> None`
  - `clear_all(root) -> None`
  - `read_slots(root, now) -> list[Slot]` —— 过滤陈旧槽位并统计标记数
  - `prune_orphans(root, now) -> None` —— 删无主标记目录与超时标记文件

- [ ] **Step 1: 写失败测试**

`tests/test_store.py`：

```python
import json
import time

from tasklight import store
from tasklight.state import SESSION_BUSY, SESSION_IDLE


def test_清洗非法字符():
    assert store.sanitize_id("a/../b c") == "a____b_c"


def test_清洗空值给出兜底名():
    assert store.sanitize_id("") == "unknown"


def test_写槽位后能读回(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY, cwd="E:\\p")
    slots = store.read_slots(tmp_path, now=time.time())
    assert len(slots) == 1
    assert slots[0].session_id == "sess-1"
    assert slots[0].state == SESSION_BUSY
    assert slots[0].cwd == "E:\\p"


def test_二次写入合并而非覆盖(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY, cwd="E:\\p")
    store.write_slot(tmp_path, "sess-1", bg_since=123.0, claude_pid=42)
    slot = store.read_slots(tmp_path, now=time.time())[0]
    assert slot.cwd == "E:\\p"
    assert slot.state == SESSION_BUSY
    assert slot.bg_since == 123.0
    assert slot.claude_pid == 42


def test_陈旧槽位被丢弃(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY)
    future = time.time() + store.STALE_SECONDS + 1
    assert store.read_slots(tmp_path, now=future) == []


def test_标记增删反映在计数上(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_IDLE)
    store.mark_add(tmp_path, "agents", "sess-1", "sub_1")
    store.mark_add(tmp_path, "agents", "sess-1", "sub_2")
    store.mark_add(tmp_path, "tasks", "sess-1", "task_1")
    slot = store.read_slots(tmp_path, now=time.time())[0]
    assert slot.pending_agents == 2
    assert slot.pending_tasks == 1

    store.mark_remove(tmp_path, "agents", "sess-1", "sub_1")
    slot = store.read_slots(tmp_path, now=time.time())[0]
    assert slot.pending_agents == 1


def test_重复删除标记不报错(tmp_path):
    store.mark_remove(tmp_path, "agents", "sess-1", "never_existed")


def test_删除会话连带清掉标记(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_IDLE)
    store.mark_add(tmp_path, "agents", "sess-1", "sub_1")
    store.drop_session(tmp_path, "sess-1")
    assert store.read_slots(tmp_path, now=time.time()) == []
    assert not (tmp_path / "agents" / "sess-1").exists()


def test_清理无主标记目录(tmp_path):
    store.mark_add(tmp_path, "agents", "ghost", "sub_1")
    store.prune_orphans(tmp_path, now=time.time())
    assert not (tmp_path / "agents" / "ghost").exists()


def test_清理超时标记文件(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_IDLE)
    store.mark_add(tmp_path, "agents", "sess-1", "sub_1")
    store.prune_orphans(tmp_path, now=time.time() + store.STALE_SECONDS + 1)
    assert not (tmp_path / "agents" / "sess-1" / "sub_1").exists()


def test_清空全部(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY)
    store.mark_add(tmp_path, "agents", "sess-1", "sub_1")
    store.clear_all(tmp_path)
    assert store.read_slots(tmp_path, now=time.time()) == []


def test_损坏的槽位文件被跳过而不崩(tmp_path):
    store.write_slot(tmp_path, "good", state=SESSION_BUSY)
    (tmp_path / "sessions" / "broken.json").write_text("{ 不是 json", encoding="utf-8")
    slots = store.read_slots(tmp_path, now=time.time())
    assert [s.session_id for s in slots] == ["good"]


def test_槽位文件写的是合法json(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY)
    raw = (tmp_path / "sessions" / "sess-1.json").read_text(encoding="utf-8")
    assert json.loads(raw)["state"] == SESSION_BUSY


def test_不残留临时文件(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY)
    assert list((tmp_path / "sessions").glob("*.tmp")) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'tasklight.store'`

- [ ] **Step 3: 实现**

`tasklight/store.py`：

```python
"""槽位目录读写。只用标准库 —— hook 进程要冷启动它。"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

from .state import SESSION_IDLE, Slot

DEFAULT_ROOT = Path.home() / ".claude" / "tasklight"
STALE_SECONDS = 4 * 3600
MARK_KINDS = ("agents", "tasks")

_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")


def sanitize_id(raw) -> str:
    cleaned = _UNSAFE.sub("_", str(raw))[:128]
    return cleaned or "unknown"


def _sessions_dir(root: Path) -> Path:
    return root / "sessions"


def _mark_dir(root: Path, kind: str, session_id: str) -> Path:
    return root / kind / sanitize_id(session_id)


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_slot(root: Path, session_id: str, **fields) -> None:
    sid = sanitize_id(session_id)
    path = _sessions_dir(root) / f"{sid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**(_load_json(path) or {}), **fields}
    merged["session_id"] = sid
    merged["updated_at"] = time.time()
    tmp = path.with_name(f"{sid}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def mark_add(root: Path, kind: str, session_id: str, item_id: str) -> None:
    directory = _mark_dir(root, kind, session_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / sanitize_id(item_id)).touch()


def mark_remove(root: Path, kind: str, session_id: str, item_id: str) -> None:
    (_mark_dir(root, kind, session_id) / sanitize_id(item_id)).unlink(missing_ok=True)


def drop_session(root: Path, session_id: str) -> None:
    sid = sanitize_id(session_id)
    (_sessions_dir(root) / f"{sid}.json").unlink(missing_ok=True)
    for kind in MARK_KINDS:
        shutil.rmtree(_mark_dir(root, kind, sid), ignore_errors=True)


def clear_all(root: Path) -> None:
    shutil.rmtree(_sessions_dir(root), ignore_errors=True)
    for kind in MARK_KINDS:
        shutil.rmtree(root / kind, ignore_errors=True)


def _count_marks(root: Path, kind: str, session_id: str, now: float) -> int:
    directory = _mark_dir(root, kind, session_id)
    if not directory.is_dir():
        return 0
    fresh = 0
    for item in directory.iterdir():
        try:
            if now - item.stat().st_mtime <= STALE_SECONDS:
                fresh += 1
        except OSError:
            continue
    return fresh


def read_slots(root: Path, now: float) -> list[Slot]:
    directory = _sessions_dir(root)
    if not directory.is_dir():
        return []
    slots = []
    for path in sorted(directory.glob("*.json")):
        data = _load_json(path)
        if not data:
            continue
        updated_at = float(data.get("updated_at") or 0.0)
        if now - updated_at > STALE_SECONDS:
            continue
        sid = data.get("session_id") or path.stem
        slots.append(
            Slot(
                session_id=sid,
                state=data.get("state") or SESSION_IDLE,
                cwd=data.get("cwd") or "",
                bg_since=data.get("bg_since"),
                claude_pid=data.get("claude_pid"),
                updated_at=updated_at,
                pending_agents=_count_marks(root, "agents", sid, now),
                pending_tasks=_count_marks(root, "tasks", sid, now),
            )
        )
    return slots


def prune_orphans(root: Path, now: float) -> None:
    known = {s.session_id for s in read_slots(root, now)}
    for kind in MARK_KINDS:
        base = root / kind
        if not base.is_dir():
            continue
        for directory in base.iterdir():
            if directory.name not in known:
                shutil.rmtree(directory, ignore_errors=True)
                continue
            _prune_stale_marks(directory, now)


def _prune_stale_marks(directory: Path, now: float) -> None:
    for item in directory.iterdir():
        try:
            if now - item.stat().st_mtime > STALE_SECONDS:
                item.unlink(missing_ok=True)
        except OSError:
            continue
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_store.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add tasklight/store.py tests/test_store.py
git commit -m "feat: 槽位存储与陈旧清理"
```

---

## Task 4: winproc.py 与 hook 脚本

**Files:**
- Create: `tasklight/winproc.py`
- Create: `hooks/tasklight_hook.py`
- Test: `tests/test_winproc.py`
- Test: `tests/test_hook.py`

**Interfaces:**
- Consumes: `tasklight.store` 全部函数
- Produces:
  - `winproc.ProcRow` 冻结数据类：`pid: int`、`ppid: int`、`name: str`（小写 exe 名）
  - `winproc.snapshot() -> dict[int, ProcRow]` —— 失败返回 `{}`
  - `winproc.created_at(pid: int) -> float | None` —— epoch 秒，失败返回 `None`
  - `winproc.find_ancestor_pid(table, start_pid, target_name, max_depth=6) -> int | None`
  - `hooks.tasklight_hook.handle(payload: dict, root: Path) -> None` —— 纯分派，可直接单测

- [ ] **Step 1: 写 winproc 的失败测试**

`tests/test_winproc.py`：

```python
from tasklight.winproc import ProcRow, find_ancestor_pid, snapshot


def table(rows):
    return {r.pid: r for r in rows}


def test_沿父链找到目标进程():
    t = table([
        ProcRow(pid=100, ppid=50, name="python.exe"),
        ProcRow(pid=50, ppid=10, name="cmd.exe"),
        ProcRow(pid=10, ppid=1, name="claude.exe"),
    ])
    assert find_ancestor_pid(t, 100, "claude.exe") == 10


def test_自身即目标时返回自身():
    t = table([ProcRow(pid=10, ppid=1, name="claude.exe")])
    assert find_ancestor_pid(t, 10, "claude.exe") == 10


def test_链上没有目标时返回None():
    t = table([
        ProcRow(pid=100, ppid=50, name="python.exe"),
        ProcRow(pid=50, ppid=1, name="explorer.exe"),
    ])
    assert find_ancestor_pid(t, 100, "claude.exe") is None


def test_父链断裂时返回None():
    t = table([ProcRow(pid=100, ppid=999, name="python.exe")])
    assert find_ancestor_pid(t, 100, "claude.exe") is None


def test_超过深度上限即放弃():
    rows = [ProcRow(pid=i, ppid=i - 1, name="cmd.exe") for i in range(2, 20)]
    rows.append(ProcRow(pid=1, ppid=0, name="claude.exe"))
    assert find_ancestor_pid(table(rows), 19, "claude.exe", max_depth=3) is None


def test_自引用的进程不会死循环():
    t = table([ProcRow(pid=4, ppid=4, name="system")])
    assert find_ancestor_pid(t, 4, "claude.exe") is None


def test_真实快照能拿到当前进程():
    import os

    t = snapshot()
    assert os.getpid() in t
    assert t[os.getpid()].name.endswith(".exe")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_winproc.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'tasklight.winproc'`

- [ ] **Step 3: 实现 winproc**

`tasklight/winproc.py`：

```python
"""Win32 进程查询。纯 ctypes，无第三方依赖，全部失败都降级为空值。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INVALID_HANDLE_VALUE = -1
FILETIME_EPOCH_DELTA = 11644473600.0
FILETIME_TICKS_PER_SECOND = 1e7


@dataclass(frozen=True)
class ProcRow:
    pid: int
    ppid: int
    name: str


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def snapshot() -> dict[int, ProcRow]:
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:
        return {}
    handle = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if handle == INVALID_HANDLE_VALUE:
        return {}
    try:
        return _walk_snapshot(kernel32, handle)
    finally:
        kernel32.CloseHandle(handle)


def _walk_snapshot(kernel32, handle) -> dict[int, ProcRow]:
    entry = _PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(_PROCESSENTRY32)
    table: dict[int, ProcRow] = {}
    ok = kernel32.Process32First(handle, ctypes.byref(entry))
    while ok:
        pid = int(entry.th32ProcessID)
        table[pid] = ProcRow(
            pid=pid,
            ppid=int(entry.th32ParentProcessID),
            name=entry.szExeFile.decode("mbcs", "ignore").lower(),
        )
        ok = kernel32.Process32Next(handle, ctypes.byref(entry))
    return table


def created_at(pid: int) -> float | None:
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:
        return None
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        unused = (wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME())
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(unused[0]),
            ctypes.byref(unused[1]),
            ctypes.byref(unused[2]),
        )
        if not ok:
            return None
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return ticks / FILETIME_TICKS_PER_SECOND - FILETIME_EPOCH_DELTA
    finally:
        kernel32.CloseHandle(handle)


def find_ancestor_pid(
    table: dict[int, ProcRow], start_pid: int, target_name: str, max_depth: int = 6
) -> int | None:
    pid = start_pid
    seen = set()
    for _ in range(max_depth):
        row = table.get(pid)
        if row is None or pid in seen:
            return None
        if row.name == target_name:
            return pid
        seen.add(pid)
        pid = row.ppid
    return None
```

- [ ] **Step 4: 跑 winproc 测试确认通过**

Run: `python -m pytest tests/test_winproc.py -v`
Expected: 7 passed

- [ ] **Step 5: 写 hook 的失败测试**

`tests/test_hook.py`：

```python
import json
import subprocess
import sys
import time
from pathlib import Path

from hooks.tasklight_hook import handle
from tasklight import store
from tasklight.state import SESSION_BUSY, SESSION_IDLE, SESSION_WAITING

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "tasklight_hook.py"


def only_slot(tmp_path):
    slots = store.read_slots(tmp_path, now=time.time())
    assert len(slots) == 1
    return slots[0]


def test_会话开始建槽位(tmp_path):
    handle({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "E:\\p"}, tmp_path)
    slot = only_slot(tmp_path)
    assert slot.state == SESSION_IDLE
    assert slot.cwd == "E:\\p"


def test_提交提示转忙碌(tmp_path):
    handle({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "E:\\p"}, tmp_path)
    handle({"hook_event_name": "UserPromptSubmit", "session_id": "s1"}, tmp_path)
    assert only_slot(tmp_path).state == SESSION_BUSY


def test_权限通知转等待(tmp_path):
    handle(
        {
            "hook_event_name": "Notification",
            "session_id": "s1",
            "notification_type": "permission_prompt",
        },
        tmp_path,
    )
    assert only_slot(tmp_path).state == SESSION_WAITING


def test_其他类型通知不改状态(tmp_path):
    handle({"hook_event_name": "SessionStart", "session_id": "s1"}, tmp_path)
    handle(
        {"hook_event_name": "Notification", "session_id": "s1", "notification_type": "auth_success"},
        tmp_path,
    )
    assert only_slot(tmp_path).state == SESSION_IDLE


def test_停止转空闲(tmp_path):
    handle({"hook_event_name": "UserPromptSubmit", "session_id": "s1"}, tmp_path)
    handle({"hook_event_name": "Stop", "session_id": "s1"}, tmp_path)
    assert only_slot(tmp_path).state == SESSION_IDLE


def test_停止失败也转空闲(tmp_path):
    handle({"hook_event_name": "UserPromptSubmit", "session_id": "s1"}, tmp_path)
    handle({"hook_event_name": "StopFailure", "session_id": "s1"}, tmp_path)
    assert only_slot(tmp_path).state == SESSION_IDLE


def test_子agent起停配对(tmp_path):
    handle({"hook_event_name": "SessionStart", "session_id": "s1"}, tmp_path)
    handle({"hook_event_name": "SubagentStart", "session_id": "s1", "agent_id": "a1"}, tmp_path)
    handle({"hook_event_name": "SubagentStart", "session_id": "s1", "agent_id": "a2"}, tmp_path)
    assert only_slot(tmp_path).pending_agents == 2
    handle({"hook_event_name": "SubagentStop", "session_id": "s1", "agent_id": "a1"}, tmp_path)
    assert only_slot(tmp_path).pending_agents == 1


def test_任务起停配对(tmp_path):
    handle({"hook_event_name": "SessionStart", "session_id": "s1"}, tmp_path)
    handle({"hook_event_name": "TaskCreated", "session_id": "s1", "task_id": "t1"}, tmp_path)
    assert only_slot(tmp_path).pending_tasks == 1
    handle({"hook_event_name": "TaskCompleted", "session_id": "s1", "task_id": "t1"}, tmp_path)
    assert only_slot(tmp_path).pending_tasks == 0


def test_会话结束清空槽位与标记(tmp_path):
    handle({"hook_event_name": "SessionStart", "session_id": "s1"}, tmp_path)
    handle({"hook_event_name": "SubagentStart", "session_id": "s1", "agent_id": "a1"}, tmp_path)
    handle({"hook_event_name": "SessionEnd", "session_id": "s1"}, tmp_path)
    assert store.read_slots(tmp_path, now=time.time()) == []
    assert not (tmp_path / "agents" / "s1").exists()


def test_后台bash记录时刻与pid(tmp_path):
    handle({"hook_event_name": "SessionStart", "session_id": "s1"}, tmp_path)
    before = time.time()
    handle(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "npm run build", "run_in_background": True},
        },
        tmp_path,
    )
    slot = only_slot(tmp_path)
    assert slot.bg_since is not None and slot.bg_since >= before


def test_前台bash不记录后台时刻(tmp_path):
    handle({"hook_event_name": "SessionStart", "session_id": "s1"}, tmp_path)
    handle(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        },
        tmp_path,
    )
    assert only_slot(tmp_path).bg_since is None


def test_非bash工具直接忽略(tmp_path):
    handle({"hook_event_name": "SessionStart", "session_id": "s1"}, tmp_path)
    handle(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "s1",
            "tool_name": "Read",
            "tool_input": {"run_in_background": True},
        },
        tmp_path,
    )
    assert only_slot(tmp_path).bg_since is None


def test_未知事件被忽略(tmp_path):
    handle({"hook_event_name": "PreCompact", "session_id": "s1"}, tmp_path)
    assert store.read_slots(tmp_path, now=time.time()) == []


def test_缺少session_id时不落盘(tmp_path):
    handle({"hook_event_name": "UserPromptSubmit"}, tmp_path)
    assert store.read_slots(tmp_path, now=time.time()) == []


def test_畸形输入脚本仍以0退出():
    result = subprocess.run(
        [sys.executable, str(HOOK)], input="不是 json", capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0


def test_空输入脚本仍以0退出():
    result = subprocess.run(
        [sys.executable, str(HOOK)], input="", capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0


def test_合法输入脚本以0退出并静默():
    payload = json.dumps({"hook_event_name": "PreCompact", "session_id": "s1"})
    result = subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0
    assert result.stdout == ""
```

- [ ] **Step 6: 跑测试确认失败**

Run: `python -m pytest tests/test_hook.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'hooks'`

- [ ] **Step 7: 实现 hook**

先建空文件 `hooks/__init__.py`，再写 `hooks/tasklight_hook.py`：

```python
"""Claude Code hook 入口。任何异常都吞掉并以 0 退出 —— 红绿灯坏掉绝不能拖累写代码。"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tasklight import store, winproc  # noqa: E402
from tasklight.state import SESSION_BUSY, SESSION_IDLE, SESSION_WAITING  # noqa: E402

PERMISSION_PROMPT = "permission_prompt"
STATE_EVENTS = {
    "SessionStart": SESSION_IDLE,
    "UserPromptSubmit": SESSION_BUSY,
    "Stop": SESSION_IDLE,
    "StopFailure": SESSION_IDLE,
}


def handle(payload: dict, root: Path) -> None:
    event = payload.get("hook_event_name")
    session_id = payload.get("session_id")
    if not event or not session_id:
        return

    if event in STATE_EVENTS:
        _write_state(root, session_id, STATE_EVENTS[event], payload)
    elif event == "Notification":
        if payload.get("notification_type") == PERMISSION_PROMPT:
            store.write_slot(root, session_id, state=SESSION_WAITING)
    elif event == "SubagentStart":
        store.mark_add(root, "agents", session_id, payload.get("agent_id", "unknown"))
    elif event == "SubagentStop":
        store.mark_remove(root, "agents", session_id, payload.get("agent_id", "unknown"))
    elif event == "TaskCreated":
        store.mark_add(root, "tasks", session_id, payload.get("task_id", "unknown"))
    elif event == "TaskCompleted":
        store.mark_remove(root, "tasks", session_id, payload.get("task_id", "unknown"))
    elif event == "SessionEnd":
        store.drop_session(root, session_id)
    elif event == "PostToolUse":
        _note_background_bash(root, session_id, payload)


def _write_state(root: Path, session_id: str, state: str, payload: dict) -> None:
    fields = {"state": state}
    if payload.get("cwd"):
        fields["cwd"] = payload["cwd"]
    store.write_slot(root, session_id, **fields)


def _note_background_bash(root: Path, session_id: str, payload: dict) -> None:
    if payload.get("tool_name") != "Bash":
        return
    tool_input = payload.get("tool_input") or {}
    if not tool_input.get("run_in_background"):
        return
    claude_pid = winproc.find_ancestor_pid(winproc.snapshot(), os.getpid(), "claude.exe")
    store.write_slot(root, session_id, bg_since=time.time(), claude_pid=claude_pid)


def main() -> None:
    payload = json.loads(sys.stdin.read())
    handle(payload, store.DEFAULT_ROOT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if os.environ.get("TASKLIGHT_DEBUG"):
            import traceback

            log = store.DEFAULT_ROOT / "hook.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as f:
                f.write(f"{time.time()} {traceback.format_exc()}\n")
    sys.exit(0)
```

- [ ] **Step 8: 跑测试确认通过**

Run: `python -m pytest tests/test_hook.py -v`
Expected: 17 passed

- [ ] **Step 9: 若 Task 1 结论要求，修正 session_id 归属**

打开 `docs/hook-payload-findings.md` 看第 1 问的结论。若 `SubagentStart.session_id` **不等于**主会话 id，把 `handle()` 中 `SubagentStart` / `SubagentStop` 两个分支取 session 的方式改为该文档记录的主会话字段名，并在 `tests/test_hook.py` 补一条对应测试。若相同则跳过本步。

- [ ] **Step 10: Commit**

```bash
git add tasklight/winproc.py hooks/__init__.py hooks/tasklight_hook.py tests/test_winproc.py tests/test_hook.py
git commit -m "feat: Win32 进程查询与 hook 事件分派"
```

---

## Task 5: probe.py 后台活动探测

**Files:**
- Create: `tasklight/probe.py`
- Test: `tests/test_probe.py`

**Interfaces:**
- Consumes: `tasklight.winproc.ProcRow` / `snapshot` / `created_at`，`tasklight.state.Slot`
- Produces:
  - `GRACE_SECONDS: float` = `2.0`
  - `descendants(table, root_pid) -> set[int]`
  - `has_background_activity(table, created_at_fn, marks, grace=GRACE_SECONDS) -> bool`，`marks: list[tuple[int, float]]` 即 `(claude_pid, bg_since)`
  - `marks_from_slots(slots) -> list[tuple[int, float]]` —— 挑出 `claude_pid` 与 `bg_since` 都非空的槽位
  - `any_claude_alive(table) -> bool`
  - `scan(slots) -> tuple[bool, bool]` —— 真实系统入口，返回 `(claude 是否存活, 是否有后台活动)`。一次 `snapshot()` 同时供两项判断使用

- [ ] **Step 1: 写失败测试**

`tests/test_probe.py`：

```python
from tasklight.probe import (
    any_claude_alive,
    descendants,
    has_background_activity,
    marks_from_slots,
)
from tasklight.state import SESSION_IDLE, Slot
from tasklight.winproc import ProcRow

CLAUDE = 100
BG_SINCE = 1000.0


def table(rows):
    return {r.pid: r for r in rows}


def base_table():
    return table([
        ProcRow(pid=CLAUDE, ppid=1, name="claude.exe"),
        ProcRow(pid=200, ppid=CLAUDE, name="cmd.exe"),
        ProcRow(pid=300, ppid=200, name="node.exe"),
    ])


def times(mapping):
    return lambda pid: mapping.get(pid)


def test_枚举后代含孙进程():
    assert descendants(base_table(), CLAUDE) == {200, 300}


def test_枚举后代不含自身():
    assert CLAUDE not in descendants(base_table(), CLAUDE)


def test_环形父子关系不会死循环():
    t = table([
        ProcRow(pid=1, ppid=2, name="a.exe"),
        ProcRow(pid=2, ppid=1, name="b.exe"),
    ])
    assert descendants(t, 1) == {2}


def test_mcp进程早于后台时刻不算命中():
    fn = times({200: BG_SINCE - 600, 300: BG_SINCE - 600})
    assert has_background_activity(base_table(), fn, [(CLAUDE, BG_SINCE)]) is False


def test_后台时刻之后创建的进程算命中():
    fn = times({200: BG_SINCE - 600, 300: BG_SINCE + 1})
    assert has_background_activity(base_table(), fn, [(CLAUDE, BG_SINCE)]) is True


def test_宽限期内略早的进程也算命中():
    fn = times({200: BG_SINCE - 1.0, 300: None})
    assert has_background_activity(base_table(), fn, [(CLAUDE, BG_SINCE)], grace=2.0) is True


def test_pid被复用为其他进程时跳过():
    t = table([
        ProcRow(pid=CLAUDE, ppid=1, name="chrome.exe"),
        ProcRow(pid=200, ppid=CLAUDE, name="cmd.exe"),
    ])
    fn = times({200: BG_SINCE + 10})
    assert has_background_activity(t, fn, [(CLAUDE, BG_SINCE)]) is False


def test_claude进程已消失时跳过():
    fn = times({200: BG_SINCE + 10})
    assert has_background_activity({}, fn, [(CLAUDE, BG_SINCE)]) is False


def test_无标记时直接为假():
    assert has_background_activity(base_table(), times({}), []) is False


def test_取不到创建时间的进程被忽略():
    assert has_background_activity(base_table(), times({}), [(CLAUDE, BG_SINCE)]) is False


def test_多会话中任一命中即为真():
    t = table([
        ProcRow(pid=CLAUDE, ppid=1, name="claude.exe"),
        ProcRow(pid=200, ppid=CLAUDE, name="cmd.exe"),
        ProcRow(pid=400, ppid=1, name="claude.exe"),
        ProcRow(pid=500, ppid=400, name="cmd.exe"),
    ])
    fn = times({200: BG_SINCE - 600, 500: BG_SINCE + 5})
    assert has_background_activity(t, fn, [(CLAUDE, BG_SINCE), (400, BG_SINCE)]) is True


def slot(pid, bg):
    return Slot(
        session_id="s",
        state=SESSION_IDLE,
        cwd="",
        bg_since=bg,
        claude_pid=pid,
        updated_at=0.0,
        pending_agents=0,
        pending_tasks=0,
    )


def test_只挑出有完整后台信息的槽位():
    slots = [slot(CLAUDE, BG_SINCE), slot(None, BG_SINCE), slot(CLAUDE, None)]
    assert marks_from_slots(slots) == [(CLAUDE, BG_SINCE)]


def test_检测claude是否存活():
    assert any_claude_alive(base_table()) is True
    assert any_claude_alive(table([ProcRow(pid=1, ppid=0, name="explorer.exe")])) is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_probe.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'tasklight.probe'`

- [ ] **Step 3: 实现**

`tasklight/probe.py`：

```python
"""后台活动探测。

MCP server 与后台 Bash 在进程树上同形（都是 claude.exe 经 shell 派生），
只能靠创建时间区分：MCP 创建于会话启动时，后台 Bash 创建于 bg_since 时刻。
"""
from __future__ import annotations

from collections.abc import Callable

from .state import Slot
from .winproc import ProcRow, created_at, snapshot

GRACE_SECONDS = 2.0
CLAUDE_EXE = "claude.exe"


def descendants(table: dict[int, ProcRow], root_pid: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for row in table.values():
        children.setdefault(row.ppid, []).append(row.pid)

    found: set[int] = set()
    queue = list(children.get(root_pid, []))
    while queue:
        pid = queue.pop()
        if pid in found or pid == root_pid:
            continue
        found.add(pid)
        queue.extend(children.get(pid, []))
    return found


def has_background_activity(
    table: dict[int, ProcRow],
    created_at_fn: Callable[[int], float | None],
    marks: list[tuple[int, float]],
    grace: float = GRACE_SECONDS,
) -> bool:
    for claude_pid, bg_since in marks:
        row = table.get(claude_pid)
        if row is None or row.name != CLAUDE_EXE:
            continue
        threshold = bg_since - grace
        for pid in descendants(table, claude_pid):
            timestamp = created_at_fn(pid)
            if timestamp is not None and timestamp >= threshold:
                return True
    return False


def marks_from_slots(slots: list[Slot]) -> list[tuple[int, float]]:
    return [
        (s.claude_pid, s.bg_since)
        for s in slots
        if s.claude_pid is not None and s.bg_since is not None
    ]


def any_claude_alive(table: dict[int, ProcRow]) -> bool:
    return any(row.name == CLAUDE_EXE for row in table.values())


def scan(slots: list[Slot]) -> tuple[bool, bool]:
    """真实系统入口。返回 (claude 是否存活, 是否有后台活动)，共用同一份进程快照。"""
    table = snapshot()
    if not any_claude_alive(table):
        return False, False
    marks = marks_from_slots(slots)
    if not marks:
        return True, False
    return True, has_background_activity(table, created_at, marks)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_probe.py -v`
Expected: 13 passed

- [ ] **Step 5: 全量回归**

Run: `python -m pytest -v`
Expected: 全部通过（62 项）

- [ ] **Step 6: Commit**

```bash
git add tasklight/probe.py tests/test_probe.py
git commit -m "feat: 基于进程创建时间的后台活动探测"
```

---

## Task 6: widget.py 悬浮窗

GUI 不写自动化测试，用一个手动驱动脚本验证四种灯态。

**Files:**
- Create: `tasklight/widget.py`
- Create: `scripts/preview_widget.py`

**Interfaces:**
- Consumes: `tasklight.state.Light` / `LIGHT_LABELS`
- Produces:
  - `TrafficLightWidget(root: tk.Tk, on_exit: Callable[[], None])`
  - `.render(light: Light) -> None` —— 幂等，同一灯色重复调用无副作用
  - `.show() -> None` / `.hide() -> None`
  - `.tick_blink() -> None` —— 由主循环每 `BLINK_MS` 调一次，驱动红灯闪烁

- [ ] **Step 1: 实现悬浮窗**

`tasklight/widget.py`：

```python
"""置顶悬浮窗。透明抠色实现圆角，左键拖拽移动。"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from .state import LIGHT_LABELS, Light

WIDTH, HEIGHT = 56, 196
RADIUS = 17
CHROMA = "#ff00ff"
PANEL = "#101010"
TEXT_COLOR = "#d8d8d8"
BLINK_MS = 500
MARGIN_RIGHT = 24

BRIGHT = {"red": "#ff2a2a", "orange": "#ff9500", "green": "#22c55e"}
DIM = {"red": "#3d0000", "orange": "#3d2400", "green": "#052616"}
LIGHT_TO_LAMP = {
    Light.RED_BLINK: "red",
    Light.RED: "red",
    Light.ORANGE: "orange",
    Light.GREEN: "green",
}
LAMP_ORDER = ("red", "orange", "green")


class TrafficLightWidget:
    def __init__(self, root: tk.Tk, on_exit: Callable[[], None]):
        self._root = root
        self._on_exit = on_exit
        self._light = Light.GREEN
        self._blink_on = True
        self._drag_origin = (0, 0)
        self._build()

    def _build(self) -> None:
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-transparentcolor", CHROMA)
        self._root.configure(bg=CHROMA)
        self._place_at_right_edge()

        self._canvas = tk.Canvas(
            self._root, width=WIDTH, height=HEIGHT, bg=CHROMA, highlightthickness=0
        )
        self._canvas.pack()
        self._draw_panel()
        self._lamps = {name: self._draw_lamp(i, name) for i, name in enumerate(LAMP_ORDER)}
        self._label = self._canvas.create_text(
            WIDTH // 2, HEIGHT - 18, text="", fill=TEXT_COLOR, font=("Microsoft YaHei UI", 8)
        )
        self._bind_events()
        self.render(Light.GREEN)

    def _place_at_right_edge(self) -> None:
        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        x = screen_w - WIDTH - MARGIN_RIGHT
        y = (screen_h - HEIGHT) // 2
        self._root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    def _draw_panel(self) -> None:
        self._rounded_rect(0, 0, WIDTH, HEIGHT, 14, PANEL)

    def _rounded_rect(self, x1, y1, x2, y2, r, color) -> None:
        c = self._canvas
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color)
        c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline=color)
        for cx, cy in ((x1, y1), (x2 - 2 * r, y1), (x1, y2 - 2 * r), (x2 - 2 * r, y2 - 2 * r)):
            c.create_oval(cx, cy, cx + 2 * r, cy + 2 * r, fill=color, outline=color)

    def _draw_lamp(self, index: int, name: str) -> int:
        cx = WIDTH // 2
        cy = 30 + index * 48
        return self._canvas.create_oval(
            cx - RADIUS, cy - RADIUS, cx + RADIUS, cy + RADIUS, fill=DIM[name], outline=""
        )

    def _bind_events(self) -> None:
        self._canvas.bind("<Button-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<Button-3>", lambda _e: self._on_exit())

    def _on_press(self, event) -> None:
        self._drag_origin = (event.x, event.y)

    def _on_drag(self, event) -> None:
        dx = event.x - self._drag_origin[0]
        dy = event.y - self._drag_origin[1]
        self._root.geometry(f"+{self._root.winfo_x() + dx}+{self._root.winfo_y() + dy}")

    def render(self, light: Light) -> None:
        self._light = light
        self._paint()

    def tick_blink(self) -> None:
        if self._light is not Light.RED_BLINK:
            return
        self._blink_on = not self._blink_on
        self._paint()

    def _paint(self) -> None:
        active = LIGHT_TO_LAMP[self._light]
        lit = self._blink_on or self._light is not Light.RED_BLINK
        for name, item in self._lamps.items():
            on = name == active and lit
            self._canvas.itemconfigure(item, fill=BRIGHT[name] if on else DIM[name])
        self._canvas.itemconfigure(self._label, text=LIGHT_LABELS[self._light])

    def show(self) -> None:
        self._root.deiconify()

    def hide(self) -> None:
        self._root.withdraw()
```

- [ ] **Step 2: 写预览脚本**

`scripts/preview_widget.py`：

```python
"""手动验证：每 2 秒切换一种灯态，右键退出。"""
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tasklight.state import Light
from tasklight.widget import BLINK_MS, TrafficLightWidget

SEQUENCE = [Light.GREEN, Light.ORANGE, Light.RED, Light.RED_BLINK]


def main():
    root = tk.Tk()
    widget = TrafficLightWidget(root, on_exit=root.destroy)
    index = {"value": 0}

    def cycle():
        widget.render(SEQUENCE[index["value"] % len(SEQUENCE)])
        index["value"] += 1
        root.after(2000, cycle)

    def blink():
        widget.tick_blink()
        root.after(BLINK_MS, blink)

    cycle()
    blink()
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 手动验证**

Run: `python scripts/preview_widget.py`

逐条确认：

1. 窗口出现在屏幕右侧垂直居中，黑色圆角，无边框、无任务栏图标
2. 四种灯态依次切换，只有对应那盏亮，其余保持暗色
3. `RED_BLINK` 时红灯以 500ms 明暗闪烁；其余灯态常亮不闪
4. 底部文字依次为 待机 / 后台运行 / 忙碌 / 等待确认
5. 左键拖拽能移动窗口
6. 右键窗口关闭
7. 圆角处透出桌面而非显示品红色方块 —— 若显示品红，说明 `-transparentcolor` 未生效，需检查 `bg` 是否与 `CHROMA` 完全一致

- [ ] **Step 4: Commit**

```bash
git add tasklight/widget.py scripts/preview_widget.py
git commit -m "feat: 置顶红绿灯悬浮窗"
```

---

## Task 7: tray.py 与 main.py 组装

**Files:**
- Create: `tasklight/tray.py`
- Create: `main.py`
- Create: `start.cmd`

**Interfaces:**
- Consumes: `tasklight.state`（`Light` / `resolve` / `resolve_without_probe` / `summarize`）、`tasklight.store`（`read_slots` / `prune_orphans` / `clear_all` / `DEFAULT_ROOT`）、`tasklight.probe.scan`、`tasklight.widget.TrafficLightWidget`
- Produces:
  - `TrayIcon(on_toggle: Callable[[], None], on_exit: Callable[[], None])`
  - `.start() -> None` / `.stop() -> None` / `.update(light: Light, tooltip: str) -> None`
  - `main.App` —— 整个应用

- [ ] **Step 1: 实现托盘**

`tasklight/tray.py`：

```python
"""系统托盘图标。pystray 在自己的线程跑消息循环，回调不直接碰 tkinter。"""
from __future__ import annotations

from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

from .state import Light

ICON_SIZE = 64
DOT_INSET = 6
ICON_COLORS = {
    Light.RED_BLINK: "#ff2a2a",
    Light.RED: "#ff2a2a",
    Light.ORANGE: "#ff9500",
    Light.GREEN: "#22c55e",
}


def _make_icon(light: Light) -> Image.Image:
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        (DOT_INSET, DOT_INSET, ICON_SIZE - DOT_INSET, ICON_SIZE - DOT_INSET),
        fill=ICON_COLORS[light],
    )
    return image


class TrayIcon:
    def __init__(self, on_toggle: Callable[[], None], on_exit: Callable[[], None]):
        menu = pystray.Menu(
            pystray.MenuItem("显示/隐藏悬浮窗", lambda _i, _item: on_toggle(), default=True),
            pystray.MenuItem("退出", lambda _i, _item: on_exit()),
        )
        self._icon = pystray.Icon("tasklight", _make_icon(Light.GREEN), "TaskLight", menu)
        self._current: tuple[Light, str] | None = None

    def start(self) -> None:
        self._icon.run_detached()

    def stop(self) -> None:
        self._icon.stop()

    def update(self, light: Light, tooltip: str) -> None:
        if self._current == (light, tooltip):
            return
        self._current = (light, tooltip)
        self._icon.icon = _make_icon(light)
        self._icon.title = tooltip
```

- [ ] **Step 2: 实现主程序**

`main.py`：

```python
"""TaskLight 主程序。手动启动，托盘右键退出。"""
from __future__ import annotations

import time
import tkinter as tk

from tasklight import probe, store
from tasklight.state import resolve, summarize
from tasklight.tray import TrayIcon
from tasklight.widget import BLINK_MS, TrafficLightWidget

TICK_MS = 400
SCAN_INTERVAL = 2.0


class App:
    def __init__(self):
        self._root = tk.Tk()
        self._widget = TrafficLightWidget(self._root, on_exit=self.quit)
        self._tray = TrayIcon(on_toggle=self._toggle_widget, on_exit=self._request_quit)
        self._visible = True
        self._scan_at = 0.0
        self._background_active = False
        self._root.protocol("WM_DELETE_WINDOW", self.quit)

    def run(self) -> None:
        self._tray.start()
        self._tick()
        self._blink()
        self._root.mainloop()

    def _tick(self) -> None:
        now = time.time()
        store.prune_orphans(store.DEFAULT_ROOT, now)
        slots = self._rescan(store.read_slots(store.DEFAULT_ROOT, now), now)
        light = resolve(slots, self._background_active)
        self._widget.render(light)
        self._tray.update(light, summarize(slots, light))
        self._root.after(TICK_MS, self._tick)

    def _rescan(self, slots, now: float):
        """按 SCAN_INTERVAL 节流地扫一次进程：既校验 claude 存活，也判定后台活动。

        存活校验必须无条件做 —— 若只在「全空闲」时才扫，会话在 busy 状态下被强杀
        就会永远停在红灯，而这正是该兜底要防的情况。
        """
        if not slots or now - self._scan_at < SCAN_INTERVAL:
            return slots
        self._scan_at = now
        alive, self._background_active = probe.scan(slots)
        if alive:
            return slots
        store.clear_all(store.DEFAULT_ROOT)
        return []

    def _blink(self) -> None:
        self._widget.tick_blink()
        self._root.after(BLINK_MS, self._blink)

    def _toggle_widget(self) -> None:
        self._root.after(0, self._apply_toggle)

    def _apply_toggle(self) -> None:
        self._visible = not self._visible
        self._widget.show() if self._visible else self._widget.hide()

    def _request_quit(self) -> None:
        self._root.after(0, self.quit)

    def quit(self) -> None:
        self._tray.stop()
        self._root.destroy()


if __name__ == "__main__":
    App().run()
```

- [ ] **Step 3: 写启动脚本**

`start.cmd`：

```bat
@echo off
cd /d "%~dp0"
start "" pythonw main.py
```

- [ ] **Step 4: 手动验证基本运行**

Run: `python main.py`（先用 `python` 而非 `pythonw`，好看到报错）

确认：

1. 悬浮窗出现，托盘出现同色圆点
2. 托盘悬停显示 `待机`
3. 托盘左键点击（默认项）能隐藏 / 显示悬浮窗
4. 托盘右键 → 退出，进程干净结束，无残留窗口

- [ ] **Step 5: 手动验证状态联动**

**前置条件：至少开着一个 Claude Code 会话。** 存活兜底会在没有任何 `claude.exe` 时清空全部槽位，手工造的槽位会在 2 秒内被抹掉，验证必然失败。

先手工造槽位，确认 GUI 正确反应（此时 hooks 尚未安装）：

```bash
python -c "from tasklight import store; store.write_slot(store.DEFAULT_ROOT, 'manual-1', state='busy', cwd='E:/test')"
```
Expected: 红灯常亮，tooltip 显示 `忙碌 · 1 会话`

```bash
python -c "from tasklight import store; store.write_slot(store.DEFAULT_ROOT, 'manual-1', state='waiting')"
```
Expected: 红灯开始闪烁，tooltip 显示 `等待确认 · 1 会话`

```bash
python -c "from tasklight import store; store.write_slot(store.DEFAULT_ROOT, 'manual-1', state='idle'); store.mark_add(store.DEFAULT_ROOT, 'agents', 'manual-1', 'a1')"
```
Expected: 橙灯常亮，tooltip 显示 `后台运行 · 后台 1`

```bash
python -c "from tasklight import store; store.drop_session(store.DEFAULT_ROOT, 'manual-1')"
```
Expected: 绿灯常亮，tooltip 显示 `待机`

- [ ] **Step 6: 验证 pythonw 无黑窗**

Run: `start.cmd`（双击或命令行执行）
Expected: 悬浮窗与托盘正常出现，**没有**残留黑色控制台窗口。托盘右键退出后，任务管理器中无 `pythonw.exe` 残留

- [ ] **Step 7: Commit**

```bash
git add tasklight/tray.py main.py start.cmd
git commit -m "feat: 托盘图标与主程序组装"
```

---

## Task 8: install_hooks.py 与端到端验收

**Files:**
- Create: `install_hooks.py`
- Test: `tests/test_install_hooks.py`
- Create: `README.md`

**Interfaces:**
- Consumes: 无（独立脚本）
- Produces:
  - `HOOK_ENTRIES: dict[str, list[dict]]` —— 要合并的 hooks 配置
  - `merge_hooks(existing: dict, entries: dict, command: str) -> dict` —— 纯函数，幂等
  - `install(settings_path: Path, hook_path: Path) -> bool` —— 返回是否发生了改动

- [ ] **Step 1: 写失败测试**

`tests/test_install_hooks.py`：

```python
import json

from install_hooks import HOOK_ENTRIES, install, merge_hooks

COMMAND = 'python "E:/Github/TaskLight/hooks/tasklight_hook.py"'


def test_空配置时装入全部事件():
    merged = merge_hooks({}, HOOK_ENTRIES, COMMAND)
    assert set(merged) == set(HOOK_ENTRIES)


def test_保留他人已有的条目():
    existing = {
        "PostToolUse": [
            {
                "matcher": "Write|Edit",
                "hooks": [{"type": "command", "command": "python other.py"}],
            }
        ]
    }
    merged = merge_hooks(existing, HOOK_ENTRIES, COMMAND)
    commands = [h["command"] for entry in merged["PostToolUse"] for h in entry["hooks"]]
    assert "python other.py" in commands
    assert COMMAND in commands


def test_重复执行不重复添加():
    once = merge_hooks({}, HOOK_ENTRIES, COMMAND)
    twice = merge_hooks(once, HOOK_ENTRIES, COMMAND)
    assert once == twice


def test_不修改传入的原配置():
    existing = {"PostToolUse": []}
    merge_hooks(existing, HOOK_ENTRIES, COMMAND)
    assert existing == {"PostToolUse": []}


def test_安装会写备份(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    install(settings, tmp_path / "hooks" / "tasklight_hook.py")
    assert (tmp_path / "settings.json.bak").exists()
    assert json.loads(settings.read_text(encoding="utf-8"))["model"] == "opus"


def test_二次安装不再改动(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({}), encoding="utf-8")
    hook = tmp_path / "hooks" / "tasklight_hook.py"
    assert install(settings, hook) is True
    assert install(settings, hook) is False


def test_安装后配置仍是合法json(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({}), encoding="utf-8")
    install(settings, tmp_path / "hooks" / "tasklight_hook.py")
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "SessionStart" in data["hooks"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_install_hooks.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'install_hooks'`

- [ ] **Step 3: 实现**

`install_hooks.py`：

```python
"""把 TaskLight 的 hooks 幂等合并进 ~/.claude/settings.json。"""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
HOOK_PATH = Path(__file__).resolve().parent / "hooks" / "tasklight_hook.py"
TIMEOUT_SECONDS = 10

HOOK_ENTRIES = {
    "SessionStart": [{}],
    "UserPromptSubmit": [{}],
    "Stop": [{}],
    "StopFailure": [{}],
    "SubagentStart": [{}],
    "SubagentStop": [{}],
    "TaskCreated": [{}],
    "TaskCompleted": [{}],
    "SessionEnd": [{}],
    "Notification": [{"matcher": "permission_prompt"}],
    "PostToolUse": [{"matcher": "Bash"}],
}


def _hook_block(command: str) -> dict:
    return {"type": "command", "command": command, "timeout": TIMEOUT_SECONDS}


def _already_present(entries: list, command: str) -> bool:
    return any(
        hook.get("command") == command
        for entry in entries
        for hook in entry.get("hooks", [])
    )


def merge_hooks(existing: dict, entries: dict, command: str) -> dict:
    merged = copy.deepcopy(existing)
    for event, specs in entries.items():
        current = merged.setdefault(event, [])
        if _already_present(current, command):
            continue
        for spec in specs:
            entry = {**spec, "hooks": [_hook_block(command)]}
            current.append(entry)
    return merged


def install(settings_path: Path, hook_path: Path) -> bool:
    command = f'python "{hook_path.as_posix()}"'
    settings = _load(settings_path)
    merged_hooks = merge_hooks(settings.get("hooks", {}), HOOK_ENTRIES, command)
    if merged_hooks == settings.get("hooks", {}):
        return False

    if settings_path.exists():
        shutil.copy2(settings_path, settings_path.with_suffix(".json.bak"))
    settings["hooks"] = merged_hooks
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    before = set(_load(SETTINGS_PATH).get("hooks", {}))
    changed = install(SETTINGS_PATH, HOOK_PATH)
    if not changed:
        print("hooks 已是最新，无需改动。")
        return 0
    after = set(_load(SETTINGS_PATH).get("hooks", {}))
    print(f"已写入 {SETTINGS_PATH}")
    print(f"备份： {SETTINGS_PATH.with_suffix('.json.bak')}")
    print(f"新增事件：{', '.join(sorted(after - before)) or '（仅在已有事件下追加条目）'}")
    print("重启 Claude Code 后生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_install_hooks.py -v`
Expected: 7 passed

- [ ] **Step 5: 全量回归**

Run: `python -m pytest -v`
Expected: 全部通过（69 项）

- [ ] **Step 6: 真机安装 hooks**

Run: `python install_hooks.py`

确认输出提到了备份路径，然后核对 `~\.claude\settings.json`：`PostToolUse` 下应同时存在 `verify-write-fresh`（matcher `Write|Edit`）与 TaskLight（matcher `Bash`）两个条目。

- [ ] **Step 7: 端到端验收**

重启 Claude Code，`start.cmd` 启动红绿灯，逐条走：

| 场景 | 操作 | 预期 |
|---|---|---|
| 忙碌 | 发一句话给 Claude | 提交瞬间红灯常亮，回答完转绿 |
| 等待确认 | 让 Claude 跑一条需要批准的命令 | 弹窗出现时红灯闪烁，批准后转常亮 |
| 子 Agent | 派一个子 Agent | 主会话答完后灯为橙，子 Agent 结束后转绿 |
| 后台 Bash | `ping -n 30 127.0.0.1` 后台跑 | 主会话答完后灯为橙，ping 结束后 ≤2.4s 内转绿 |
| 多窗口 | 开第二个 CLI 窗口并发一句话 | 任一窗口忙即红，两个都停才转绿 |
| VS Code | 在 VS Code 扩展里发一句话 | 同 CLI，红灯亮起 |
| 崩溃恢复 | 会话**处于忙碌（红灯）时**用任务管理器强杀全部 claude.exe | 灯在 ≤2.4s 内转绿，槽位目录被清空。必须在红灯状态下杀 —— 这正是存活兜底要防的场景 |

**后台 Bash 那条是核心验收点** —— 若 ping 期间显示绿灯，说明 `bg_since` 或 `claude_pid` 没写进去，查 `~\.claude\tasklight\sessions\*.json`；若 ping 结束后仍长期橙灯，说明有 MCP 进程创建时间晚于 `bg_since`，需要调查该进程是什么。

- [ ] **Step 8: 写 README**

`README.md`：

````markdown
# TaskLight 🚦

Windows 桌面红绿灯，余光一扫就知道 Claude Code 在忙什么。聚合所有会话（CLI + VS Code 扩展），全局一盏灯。

## 灯态

| 灯 | 含义 |
|---|---|
| 🔴 闪烁 | Claude 停下来等你批准权限 —— 不回去它就一直卡着 |
| 🔴 常亮 | Claude 正在干活，可以走开 |
| 🟠 常亮 | 前台都停了，但后台子 Agent / Task / Bash 还在跑 |
| 🟢 常亮 | 全部完成，待机 |

## 安装

```bash
python -m pip install -e .
python install_hooks.py
```

`install_hooks.py` 会把 hooks 幂等合并进 `~\.claude\settings.json`（自动备份 `.bak`，不动你已有的条目）。**重启 Claude Code** 后生效。

然后双击 `start.cmd` 启动红绿灯。左键拖拽移动，右键或托盘菜单退出。

## 卸载

1. 从 `~\.claude\settings.json` 的 `hooks` 里删掉所有 `command` 含 `tasklight_hook.py` 的条目
2. 删除 `~\.claude\tasklight\` 目录

## 已知限制

- **后台 Bash 是推断而非精确判定**。Claude Code 的后台 Bash 完成时不发任何 hook 事件（官方 issue #45781 已 closed as not planned），所以只能靠「进程创建时间晚于该会话起后台命令的时刻」来识别。常驻 MCP 进程因创建时间更早而被排除
- 探测按 2 秒节流，后台任务结束到转绿最长有 2.4 秒延迟
- 仅支持 Windows（依赖 Win32 进程 API 与 tkinter 的 `-transparentcolor`）
- 不监控 SSH / WSL 上的远程会话

## 开发

```bash
python -m pytest -v          # 全部测试
python scripts/preview_widget.py   # 手动预览四种灯态
```
````

- [ ] **Step 9: Commit**

```bash
git add install_hooks.py tests/test_install_hooks.py README.md
git commit -m "feat: hooks 安装脚本与使用文档"
```

---

## 附：自检记录

对照 spec 逐节核过，覆盖情况：

| Spec 章节 | 对应任务 |
|---|---|
| 1 需求 / 灯色语义 | Task 2（`resolve`）、Task 6（渲染） |
| 2 技术背景 | Task 1（实测验证） |
| 3.1 通信机制 | Task 3（`store`）、Task 7（tick 轮询） |
| 3.2 目录布局 | 全部任务的 Files 段 |
| 3.3 状态槽位 / `claude_pid` | Task 3、Task 4 |
| 3.4 Hook 映射 | Task 4（分派）、Task 8（settings 注册） |
| 3.5 灯色判定 | Task 2 |
| 3.6 后台探测 | Task 5 |
| 3.7 僵尸清理 | Task 3（`prune_orphans` / 陈旧过滤）、Task 7（`clear_all`） |
| 3.8 线程模型 | Task 7 |
| 3.9 渲染 | Task 6、Task 7 |
| 4 错误处理 | Task 4（hook exit 0）、Task 3（损坏文件跳过）、Task 5（探测降级） |
| 5 测试策略 | Task 2/3/4/5 的测试段 |
| 6 待验证假设 | Task 1，并在 Task 4 Step 9 设了修正点 |
