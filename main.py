"""TaskLight 主程序。手动启动，托盘右键退出。"""
from __future__ import annotations

import sys
import time
import tkinter as tk

from tasklight import config as config_module
from tasklight import store
from tasklight.settings_window import SettingsWindow
from tasklight.state import resolve, summarize
from tasklight.tray import TrayIcon
from tasklight.widget import BLINK_TICK_MS, TrafficLightWidget
from tasklight.winproc import any_claude_alive, claim_single_instance, snapshot

TICK_MS = 400
SCAN_INTERVAL = 2.0
INSTANCE_MUTEX = "Global\\TaskLight.SingleInstance"


class App:
    def __init__(self):
        self._root = tk.Tk()
        self._root.withdraw()
        self._config = config_module.load(store.DEFAULT_ROOT)
        self._window = tk.Toplevel(self._root)
        self._widget = TrafficLightWidget(self._window, self._config)
        self._settings = SettingsWindow(self._root, self._config, self._apply_config)
        self._tray = TrayIcon(
            on_toggle=self._toggle_widget,
            on_settings=self._open_settings,
            on_exit=self._request_quit,
        )
        self._visible = True
        self._scan_at = 0.0
        self._window.protocol("WM_DELETE_WINDOW", self.quit)

    def run(self) -> None:
        self._tray.start()
        self._tick()
        self._blink()
        self._root.mainloop()

    def _tick(self) -> None:
        now = time.time()
        store.prune_orphans(store.DEFAULT_ROOT, now)
        slots = self._drop_if_claude_gone(store.read_slots(store.DEFAULT_ROOT, now), now)
        light = resolve(slots)
        self._widget.render(light)
        self._tray.update(light, summarize(slots, light))
        self._root.after(TICK_MS, self._tick)

    def _drop_if_claude_gone(self, slots, now: float):
        """崩溃兜底：一个 claude.exe 都不在了就清空槽位。

        必须无条件做 —— 若只在「全空闲」时才查，会话在 busy 状态下被强杀
        就会永远停在红灯，而这正是该兜底要防的情况。扫进程约 11ms，按
        SCAN_INTERVAL 节流。
        """
        if not slots or now - self._scan_at < SCAN_INTERVAL:
            return slots
        self._scan_at = now
        if any_claude_alive(snapshot()):
            return slots
        store.clear_all(store.DEFAULT_ROOT)
        return []

    def _blink(self) -> None:
        self._widget.tick_blink()
        self._root.after(BLINK_TICK_MS, self._blink)

    # ---------- 托盘回调：都转回主线程再碰 tkinter ----------

    def _toggle_widget(self) -> None:
        self._root.after(0, self._apply_toggle)

    def _apply_toggle(self) -> None:
        self._visible = not self._visible
        self._widget.show() if self._visible else self._widget.hide()

    def _open_settings(self) -> None:
        self._root.after(0, lambda: self._settings.open(self._config))

    def _request_quit(self) -> None:
        self._root.after(0, self.quit)

    def _apply_config(self, config) -> None:
        self._config = config
        self._widget.set_config(config)
        config_module.save(store.DEFAULT_ROOT, config)

    def quit(self) -> None:
        self._tray.stop()
        self._root.destroy()


def main() -> int:
    if not claim_single_instance(INSTANCE_MUTEX):
        # 走 pythonw 启动时没有控制台，print 看不见，必须弹窗告知
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0, "TaskLight 已在运行。\n托盘图标右键可退出现有实例。", "TaskLight", 0x40
        )
        return 1
    App().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
