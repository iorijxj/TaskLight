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
