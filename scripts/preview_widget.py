"""手动验证：每 2 秒切换一种灯态，右键退出。"""
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tasklight.state import Light
from tasklight.widget import BLINK_MS, TrafficLightWidget

SEQUENCE = [Light.GREEN, Light.ORANGE, Light.RED, Light.RED_BLINK]


def main():
    root = tk.Tk()
    widget = TrafficLightWidget(root, on_exit=root.destroy)
    index = {"value": 0}

    def cycle():
        widget.render(SEQUENCE[index["value"] % len(SEQUENCE)])
        index["value"] += 1
        root.after(2000, cycle)

    def blink():
        widget.tick_blink()
        root.after(BLINK_MS, blink)

    cycle()
    blink()
    root.mainloop()


if __name__ == "__main__":
    main()
