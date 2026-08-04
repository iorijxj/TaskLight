"""系统托盘图标。pystray 在自己的线程跑消息循环，回调不直接碰 tkinter。"""
from __future__ import annotations

from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

from .state import Light

ICON_SIZE = 64
DOT_INSET = 6
ICON_COLORS = {
    Light.WAITING: "#ff2a2a",
    Light.BUSY: "#ff2a2a",
    Light.BACKGROUND: "#ff9500",
    Light.IDLE: "#22c55e",
}


def _make_icon(light: Light) -> Image.Image:
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        (DOT_INSET, DOT_INSET, ICON_SIZE - DOT_INSET, ICON_SIZE - DOT_INSET),
        fill=ICON_COLORS[light],
    )
    return image


class TrayIcon:
    def __init__(
        self,
        on_toggle: Callable[[], None],
        on_settings: Callable[[], None],
        on_exit: Callable[[], None],
    ):
        menu = pystray.Menu(
            pystray.MenuItem("显示/隐藏悬浮窗", lambda _i, _item: on_toggle(), default=True),
            pystray.MenuItem("设置", lambda _i, _item: on_settings()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda _i, _item: on_exit()),
        )
        self._icon = pystray.Icon("tasklight", _make_icon(Light.IDLE), "TaskLight", menu)
        self._light: Light | None = None
        self._tooltip: str | None = None

    def start(self) -> None:
        self._icon.run_detached()

    def stop(self) -> None:
        self._icon.stop()

    def update(self, light: Light, tooltip: str) -> None:
        """图标与 tooltip 分开判断：tooltip 里带会话数，变得比灯色勤得多，
        没必要为它重建图标。先赋值后记状态，赋值失败时下一轮会自动重试。"""
        if not self._icon.visible:
            # run_detached() 要 0.05~0.5s 才就绪，这期间 pystray 的 icon setter
            # 会静默跳过刷新。若此时就记下状态，托盘会永远定格在初始图标。
            return
        if light is not self._light:
            self._icon.icon = _make_icon(light)
            self._light = light
        if tooltip != self._tooltip:
            self._icon.title = tooltip
            self._tooltip = tooltip
