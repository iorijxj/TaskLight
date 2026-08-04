"""闪烁行为配置。存 ~/.claude/tasklight/config.json，读不到就用默认值。"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

CONFIG_FILE = "config.json"
MIN_INTERVAL_MS = 100
MAX_INTERVAL_MS = 3000


@dataclass(frozen=True)
class Config:
    blink_normal_ms: int = 600
    blink_fast_ms: int = 250
    blink_busy: bool = True
    blink_background: bool = True


def _clamp_interval(value: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(MIN_INTERVAL_MS, min(MAX_INTERVAL_MS, number))


def from_dict(data: dict) -> Config:
    """逐字段校验，坏值退回默认 —— 配置文件是用户可手改的，不能信。"""
    defaults = Config()
    if not isinstance(data, dict):
        return defaults
    return Config(
        blink_normal_ms=_clamp_interval(
            data.get("blink_normal_ms"), defaults.blink_normal_ms
        ),
        blink_fast_ms=_clamp_interval(data.get("blink_fast_ms"), defaults.blink_fast_ms),
        blink_busy=bool(data.get("blink_busy", defaults.blink_busy)),
        blink_background=bool(data.get("blink_background", defaults.blink_background)),
    )


def load(root: Path) -> Config:
    try:
        raw = json.loads((root / CONFIG_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config()
    return from_dict(raw)


def save(root: Path, config: Config) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / CONFIG_FILE
    tmp = path.with_name(f"{CONFIG_FILE}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def field_names() -> tuple[str, ...]:
    return tuple(f.name for f in fields(Config))
