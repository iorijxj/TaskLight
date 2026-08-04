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
    bg_count: int
    updated_at: float
    pending_agents: int
    pending_tasks: int

    @property
    def background_total(self) -> int:
        return self.bg_count + self.pending_agents + self.pending_tasks


def resolve(slots: list[Slot]) -> Light:
    if any(s.state == SESSION_WAITING for s in slots):
        return Light.RED_BLINK
    if any(s.state == SESSION_BUSY for s in slots):
        return Light.RED
    if any(s.background_total for s in slots):
        return Light.ORANGE
    return Light.GREEN


def summarize(slots: list[Slot], light: Light) -> str:
    parts = [LIGHT_LABELS[light]]
    active = sum(1 for s in slots if s.state in (SESSION_BUSY, SESSION_WAITING))
    pending = sum(s.background_total for s in slots)
    if active:
        parts.append(f"{active} 会话")
    if pending:
        parts.append(f"后台 {pending}")
    return " · ".join(parts)
