"""检查 hook payload 采样是否齐全。属 Task 1 的临时脚本，验证完随 dump_payload.py 一并删除。"""
import json
import sys
from collections import Counter
from pathlib import Path

# Windows 控制台默认 GBK，中文输出会炸
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DUMP = Path.home() / ".claude" / "tasklight" / "dump.jsonl"

REQUIRED = {
    "SessionStart": "会话启动（CLI 与 VS Code 各一次）",
    "SubagentStart": "子 agent 启动",
    "SubagentStop": "子 agent 结束",
    "Notification": "权限确认弹窗",
    "PostToolUse": "Bash 调用（需含一次 run_in_background）",
}


def load():
    if not DUMP.exists():
        return []
    rows = []
    for line in DUMP.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def has_background_bash(rows) -> bool:
    return any(
        r.get("hook_event_name") == "PostToolUse"
        and (r.get("tool_input") or {}).get("run_in_background")
        for r in rows
    )


def main() -> int:
    rows = load()
    if not rows:
        print("还没有任何采样数据。")
        print("确认：1) 是否新开了 CLI 窗口  2) hooks 是否已挂载")
        return 1

    counts = Counter(r.get("hook_event_name", "?") for r in rows)
    print(f"共 {len(rows)} 条采样\n")

    missing = []
    for event, desc in REQUIRED.items():
        n = counts.get(event, 0)
        mark = "OK  " if n else "缺失"
        print(f"  [{mark}] {event:16s} {n:2d} 次   {desc}")
        if not n:
            missing.append(event)

    bg = has_background_bash(rows)
    print(f"  [{'OK  ' if bg else '缺失'}] {'后台 Bash 标志':16s}      tool_input.run_in_background")
    if not bg:
        missing.append("后台 Bash")

    sessions = {r.get("session_id") for r in rows if r.get("hook_event_name") == "SessionStart"}
    print(f"\n  采到 {len(sessions)} 个不同会话的 SessionStart")
    if len(sessions) < 2:
        print("  （少于 2 个 —— VS Code 那步可能没做，或扩展未触发 hooks，这本身就是结论）")

    print()
    if missing:
        print("尚缺:", "、".join(missing))
        return 1
    print("采样齐全，可以让 Claude 出结论了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
