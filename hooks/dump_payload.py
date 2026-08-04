"""临时诊断脚本：把每次 hook 的原始 payload 追加到 dump.jsonl。验证完即删。"""
import json
import os
import sys
import time
from pathlib import Path

OUT = Path.home() / ".claude" / "tasklight" / "dump.jsonl"


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {"_unparsed": raw[:2000]}
    payload["_received_at"] = time.time()
    payload["_hook_pid"] = os.getpid()
    payload["_hook_ppid"] = os.getppid()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
