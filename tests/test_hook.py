import json
import os
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


def _run_hook_with_utf8(payload: dict, root: Path):
    """按 Claude Code 的真实方式喂 payload：UTF-8 字节流，不经 locale 编码。"""
    env = {**os.environ, "TASKLIGHT_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, "-S", str(HOOK)],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        timeout=30,
        env=env,
    )


def test_中文payload不会让hook崩掉(tmp_path):
    """Windows 上 sys.stdin.read() 按 cp936 解码 UTF-8 payload 会产生 surrogate，
    写文件时抛 UnicodeEncodeError。实测中这让所有含中文的事件静默丢失。"""
    result = _run_hook_with_utf8(
        {
            "hook_event_name": "SessionStart",
            "session_id": "zh-1",
            "cwd": "E:\\项目\\测试目录",
        },
        tmp_path,
    )
    assert result.returncode == 0
    slots = store.read_slots(tmp_path, now=time.time())
    assert len(slots) == 1
    assert slots[0].cwd == "E:\\项目\\测试目录"


def test_中文助手消息不影响状态落盘(tmp_path):
    result = _run_hook_with_utf8(
        {
            "hook_event_name": "Stop",
            "session_id": "zh-2",
            "last_assistant_message": "这是一段中文回复，含全角标点：、。！",
        },
        tmp_path,
    )
    assert result.returncode == 0
    slots = store.read_slots(tmp_path, now=time.time())
    assert len(slots) == 1
    assert slots[0].state == SESSION_IDLE


def test_中文命令描述不影响后台标记(tmp_path):
    """用后台命令，确保真正走到落盘路径 —— 前台 Bash 会提前 return，测不出编码问题。"""
    result = _run_hook_with_utf8(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "zh-3",
            "tool_name": "Bash",
            "tool_input": {
                "command": "ping 127.0.0.1",
                "description": "记录当前采样行数",
                "run_in_background": True,
            },
        },
        tmp_path,
    )
    assert result.returncode == 0
    slots = store.read_slots(tmp_path, now=time.time())
    assert len(slots) == 1
    assert slots[0].bg_since is not None


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
