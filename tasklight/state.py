"""灯色判定。纯函数，不做任何 I/O。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

SESSION_IDLE = "idle"
SESSION_BUSY = "busy"
SESSION_WAITING = "waiting"


class Light(Enum):
    """按语义命名而非按颜色 —— 颜色和闪不闪都属于表现层，由 widget 决定。"""

    WAITING = "waiting"
    BUSY = "busy"
    BACKGROUND = "background"
    IDLE = "idle"


LIGHT_LABELS = {
    Light.WAITING: "等待确认",
    Light.BUSY: "忙碌",
    Light.BACKGROUND: "后台运行",
    Light.IDLE: "待机",
}


@dataclass(frozen=True)
class Slot:
    session_id: str
    state: str
    cwd: str
    bg_count: int
    updated_at: float
    pending_agents: int
    pending_tasks: int

    @property
    def background_total(self) -> int:
        return self.bg_count + self.pending_agents + self.pending_tasks


def resolve(slots: list[Slot]) -> Light:
    if any(s.state == SESSION_WAITING for s in slots):
        return Light.WAITING
    if any(s.state == SESSION_BUSY for s in slots):
        return Light.BUSY
    if any(s.background_total for s in slots):
        return Light.BACKGROUND
    return Light.IDLE


def summarize(slots: list[Slot], light: Light) -> str:
    parts = [LIGHT_LABELS[light]]
    active = sum(1 for s in slots if s.state in (SESSION_BUSY, SESSION_WAITING))
    pending = sum(s.background_total for s in slots)
    if active:
        parts.append(f"{active} 会话")
    if pending:
        parts.append(f"后台 {pending}")
    return " · ".join(parts)
