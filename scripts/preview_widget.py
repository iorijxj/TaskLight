"""手动验证：每 2 秒切换一种灯态。关闭请用 Ctrl+C 或结束进程。"""
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tasklight.state import Light
from tasklight.config import Config
from tasklight.widget import BLINK_TICK_MS, TrafficLightWidget

SEQUENCE = [Light.IDLE, Light.BACKGROUND, Light.BUSY, Light.WAITING]


def main():
    root = tk.Tk()
    widget = TrafficLightWidget(root, Config())
    index = {"value": 0}

    def cycle():
        widget.render(SEQUENCE[index["value"] % len(SEQUENCE)])
        index["value"] += 1
        root.after(2000, cycle)

    def blink():
        widget.tick_blink()
        root.after(BLINK_TICK_MS, blink)

    cycle()
    blink()
    root.mainloop()


if __name__ == "__main__":
    main()
