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
