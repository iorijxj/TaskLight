"""置顶悬浮窗：横置红绿灯，图片背景，左键拖动，边缘等比缩放。

不提供退出入口 —— 退出只走托盘菜单，免得在灯上误点一下就关掉。
"""
from __future__ import annotations

import time
import tkinter as tk

from . import assets, layered, store
from .config import Config
from .state import Light

DEFAULT_WIDTH = 340
MIN_WIDTH = 180
MAX_WIDTH = assets.BASE_WIDTH
EDGE = 8
# 闪烁由时间戳驱动，这只是采样粒度：要支持 250ms 的快闪就得比它细得多
BLINK_TICK_MS = 50
MARGIN_RIGHT = 24

LIGHT_TO_FRAME = {
    Light.WAITING: assets.FRAME_RED_ORANGE,
    Light.BUSY: assets.FRAME_RED,
    Light.BACKGROUND: assets.FRAME_ORANGE,
    Light.IDLE: assets.FRAME_GREEN,
}
EDGE_CURSORS = {
    "e": "sb_h_double_arrow",
    "w": "sb_h_double_arrow",
    "n": "sb_v_double_arrow",
    "s": "sb_v_double_arrow",
    "se": "size_nw_se",
    "nw": "size_nw_se",
    "ne": "size_ne_sw",
    "sw": "size_ne_sw",
}


class TrafficLightWidget:
    def __init__(self, root: tk.Tk | tk.Toplevel, config: Config):
        self._root = root
        self._config = config
        self._frames = assets.build_frames()
        self._ratio = assets.aspect_ratio()
        self._light = Light.IDLE
        self._lit = True
        self._last_flip = 0.0
        self._width = DEFAULT_WIDTH
        self._drag: dict | None = None
        self._hwnd = 0
        self._build()

    # ---------- 构建 ----------

    def _build(self) -> None:
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._place_initial()
        self._root.update_idletasks()
        self._hwnd = layered.resolve_hwnd(self._root.winfo_id())
        layered.enable(self._hwnd)
        self._bind_events()
        self._paint()

    def _height(self) -> int:
        return round(self._width / self._ratio)

    def _place_initial(self) -> None:
        screen = (self._root.winfo_screenwidth(), self._root.winfo_screenheight())
        saved = store.load_window(store.DEFAULT_ROOT, screen)
        if saved:
            self._width = max(MIN_WIDTH, min(MAX_WIDTH, saved["width"]))
            self._apply_geometry(saved["x"], saved["y"])
            return
        x = screen[0] - self._width - MARGIN_RIGHT
        y = (screen[1] - self._height()) // 2
        self._apply_geometry(x, y)

    def _remember_geometry(self) -> None:
        store.save_window(
            store.DEFAULT_ROOT, self._root.winfo_x(), self._root.winfo_y(), self._width
        )

    def _apply_geometry(self, x: int, y: int) -> None:
        self._root.geometry(f"{self._width}x{self._height()}+{x}+{y}")

    def _bind_events(self) -> None:
        """刻意不绑右键：悬浮窗只负责看和拖，退出只能走托盘菜单，
        免得在灯上误点一下就把它关了。"""
        root = self._root
        root.bind("<Motion>", self._on_motion)
        root.bind("<Button-1>", self._on_press)
        root.bind("<B1-Motion>", self._on_drag_motion)
        root.bind("<ButtonRelease-1>", self._on_release)

    # ---------- 边缘检测与光标 ----------

    def _edge_at(self, x: int, y: int) -> str:
        vertical = "n" if y < EDGE else "s" if y >= self._height() - EDGE else ""
        horizontal = "w" if x < EDGE else "e" if x >= self._width - EDGE else ""
        return vertical + horizontal

    def _on_motion(self, event) -> None:
        edge = self._edge_at(event.x, event.y)
        self._root.configure(cursor=EDGE_CURSORS.get(edge, "fleur"))

    # ---------- 拖动与缩放 ----------

    def _on_press(self, event) -> None:
        self._drag = {
            "edge": self._edge_at(event.x, event.y),
            "x": event.x_root,
            "y": event.y_root,
            "width": self._width,
            "win_x": self._root.winfo_x(),
            "win_y": self._root.winfo_y(),
            "win_h": self._height(),
        }

    def _on_drag_motion(self, event) -> None:
        if not self._drag:
            return
        dx = event.x_root - self._drag["x"]
        dy = event.y_root - self._drag["y"]
        if self._drag["edge"]:
            self._resize_by(dx, dy)
        else:
            self._apply_geometry(self._drag["win_x"] + dx, self._drag["win_y"] + dy)

    def _resize_by(self, dx: int, dy: int) -> None:
        edge = self._drag["edge"]
        delta = self._width_delta(edge, dx, dy)
        width = max(MIN_WIDTH, min(MAX_WIDTH, self._drag["width"] + delta))
        self._width = width
        x, y = self._anchored_position(edge, width)
        self._apply_geometry(x, y)
        self._paint()

    def _width_delta(self, edge: str, dx: int, dy: int) -> int:
        if "e" in edge:
            return dx
        if "w" in edge:
            return -dx
        return round((dy if "s" in edge else -dy) * self._ratio)

    def _anchored_position(self, edge: str, width: int) -> tuple[int, int]:
        """缩放时固定对角，避免窗口一边缩一边跑。"""
        height = round(width / self._ratio)
        x, y = self._drag["win_x"], self._drag["win_y"]
        if "w" in edge:
            x = self._drag["win_x"] + self._drag["width"] - width
        if "n" in edge:
            y = self._drag["win_y"] + self._drag["win_h"] - height
        return x, y

    def _on_release(self, _event) -> None:
        if self._drag:
            self._remember_geometry()
        self._drag = None

    # ---------- 渲染 ----------

    def render(self, light: Light) -> None:
        """灯色没变就什么都不做 —— 闪烁由 tick_blink 驱动，避免每轮白重绘。"""
        if light is self._light:
            return
        self._light = light
        self._lit = True
        self._last_flip = time.monotonic()
        self._paint()

    def set_config(self, config: Config) -> None:
        self._config = config
        self._lit = True
        self._last_flip = time.monotonic()
        self._paint()

    def blink_interval(self) -> float | None:
        """当前灯态的闪烁间隔（秒）；None 表示常亮。

        等待确认永远闪，且用更快的节奏 —— 它是唯一「不回去就一直卡着」的状态，
        不该被用户关掉。
        """
        if self._light is Light.WAITING:
            return self._config.blink_fast_ms / 1000
        if self._light is Light.BUSY and self._config.blink_busy:
            return self._config.blink_normal_ms / 1000
        if self._light is Light.BACKGROUND and self._config.blink_background:
            return self._config.blink_normal_ms / 1000
        return None

    def tick_blink(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        interval = self.blink_interval()
        if interval is None:
            if not self._lit:
                self._lit = True
                self._paint()
            return
        if now - self._last_flip < interval:
            return
        self._last_flip = now
        self._lit = not self._lit
        self._paint()

    def _paint(self) -> None:
        if not self._hwnd:
            return
        name = LIGHT_TO_FRAME[self._light] if self._lit else assets.FRAME_DARK
        frame = self._frames[name].resize((self._width, self._height()))
        layered.paint(self._hwnd, frame)

    def show(self) -> None:
        self._root.deiconify()
        self._paint()

    def hide(self) -> None:
        self._root.withdraw()
