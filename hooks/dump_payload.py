"""临时诊断脚本：每次 hook 调用写一个独立文件，避免 append 竞争。验证完即删。"""
import json
import os
import sys
import time
from pathlib import Path

OUT_DIR = Path.home() / ".claude" / "tasklight" / "dump"
ERR_LOG = Path.home() / ".claude" / "tasklight" / "dump_error.log"


def main():
    # 同 tasklight_hook：必须自行按 UTF-8 解码，否则 Windows locale 编码会产生
    # surrogate 字符，写文件时抛 UnicodeEncodeError
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {"_unparsed": raw[:2000]}
    payload["_received_at"] = time.time()
    payload["_hook_pid"] = os.getpid()
    payload["_hook_ppid"] = os.getppid()
    payload["_tag"] = sys.argv[1] if len(sys.argv) > 1 else ""

    event = payload.get("hook_event_name", "UNKNOWN")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{payload['_received_at']:.4f}_{event}_{os.getpid()}.json"
    (OUT_DIR / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            import traceback

            ERR_LOG.parent.mkdir(parents=True, exist_ok=True)
            with ERR_LOG.open("a", encoding="utf-8") as f:
                f.write(f"=== {time.time()}\n{traceback.format_exc()}\n")
        except Exception:
            pass
    sys.exit(0)
