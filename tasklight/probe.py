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
