"""Claude Code hook 入口。任何异常都吞掉并以 0 退出 —— 红绿灯坏掉绝不能拖累写代码。"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tasklight import store  # noqa: E402
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
    # winproc 连带 ctypes，顶层 import 要 12ms，而只有这一个分支用得上。
    from tasklight import winproc

    claude_pid = winproc.find_ancestor_pid(winproc.snapshot(), os.getpid(), "claude.exe")
    store.write_slot(root, session_id, bg_since=time.time(), claude_pid=claude_pid)


def main() -> None:
    # 必须从 buffer 读原始字节自行按 UTF-8 解码：sys.stdin.read() 在 Windows 上
    # 会用 locale 编码（cp936）去解 UTF-8 的 payload，遇到解不了的字节就产生
    # surrogate 字符，写槽位时抛 UnicodeEncodeError —— 实测会让所有含中文的
    # 事件静默丢失，红绿灯彻底失灵。
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    root = Path(os.environ.get("TASKLIGHT_ROOT") or store.DEFAULT_ROOT)
    handle(json.loads(raw), root)


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
