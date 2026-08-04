"""把 TaskLight 的 hooks 幂等合并进 ~/.claude/settings.json。

用法:
    python install_hooks.py           安装
    python install_hooks.py --uninstall   卸载
"""
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


def build_command(hook_path: Path) -> str:
    """-S 跳过 site-packages 扫描，省约 17ms/次。

    hook 只用标准库并自行 sys.path.insert 项目根，因此不依赖 site —— 代价是
    hook 侧永远不能引入第三方库。
    """
    return f'python -S "{hook_path.as_posix()}"'


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
            current.append({**spec, "hooks": [_hook_block(command)]})
    return merged


def strip_hooks(existing: dict, command: str) -> dict:
    stripped = {}
    for event, entries in copy.deepcopy(existing).items():
        kept = [
            e for e in entries
            if not any(h.get("command") == command for h in e.get("hooks", []))
        ]
        if kept:
            stripped[event] = kept
    return stripped


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _apply(settings_path: Path, new_hooks: dict) -> bool:
    settings = _load(settings_path)
    if new_hooks == settings.get("hooks", {}):
        return False
    if settings_path.exists():
        shutil.copy2(settings_path, settings_path.with_suffix(".json.bak"))
    settings["hooks"] = new_hooks
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


def install(settings_path: Path, hook_path: Path) -> bool:
    command = build_command(hook_path)
    existing = _load(settings_path).get("hooks", {})
    return _apply(settings_path, merge_hooks(existing, HOOK_ENTRIES, command))


def uninstall(settings_path: Path, hook_path: Path) -> bool:
    command = build_command(hook_path)
    existing = _load(settings_path).get("hooks", {})
    return _apply(settings_path, strip_hooks(existing, command))


def main() -> int:
    removing = "--uninstall" in sys.argv
    before = set(_load(SETTINGS_PATH).get("hooks", {}))
    changed = (uninstall if removing else install)(SETTINGS_PATH, HOOK_PATH)
    if not changed:
        print("卸载：无 TaskLight 条目。" if removing else "hooks 已是最新，无需改动。")
        return 0

    after = set(_load(SETTINGS_PATH).get("hooks", {}))
    print(f"已写入 {SETTINGS_PATH}")
    print(f"备份： {SETTINGS_PATH.with_suffix('.json.bak')}")
    if removing:
        print(f"移除事件：{', '.join(sorted(before - after)) or '（仅移除已有事件下的条目）'}")
    else:
        print(f"新增事件：{', '.join(sorted(after - before)) or '（仅在已有事件下追加条目）'}")
    print("重启 Claude Code 后生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
