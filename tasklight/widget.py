"""置顶悬浮窗：横置红绿灯，图片背景，左键拖动，边缘等比缩放，右键退出。"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from . import assets, layered
from .state import Light

DEFAULT_WIDTH = 340
MIN_WIDTH = 180
MAX_WIDTH = assets.BASE_WIDTH
EDGE = 8
BLINK_MS = 500
MARGIN_RIGHT = 24

LIGHT_TO_FRAME = {
    Light.RED_BLINK: "red",
    Light.RED: "red",
    Light.ORANGE: "orange",
    Light.GREEN: "green",
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
    def __init__(self, root: tk.Tk, on_exit: Callable[[], None]):
        self._root = root
        self._on_exit = on_exit
        self._frames = assets.build_frames()
        self._ratio = assets.aspect_ratio()
        self._light = Light.GREEN
        self._blink_on = True
        self._width = DEFAULT_WIDTH
        self._drag: dict | None = None
        self._hwnd = 0
        self._build()

    # ---------- 构建 ----------

    def _build(self) -> None:
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._place_at_right_edge()
        self._root.update_idletasks()
        self._hwnd = layered.resolve_hwnd(self._root.winfo_id())
        layered.enable(self._hwnd)
        self._bind_events()
        self.render(Light.GREEN)

    def _height(self) -> int:
        return round(self._width / self._ratio)

    def _place_at_right_edge(self) -> None:
        x = self._root.winfo_screenwidth() - self._width - MARGIN_RIGHT
        y = (self._root.winfo_screenheight() - self._height()) // 2
        self._apply_geometry(x, y)

    def _apply_geometry(self, x: int, y: int) -> None:
        self._root.geometry(f"{self._width}x{self._height()}+{x}+{y}")

    def _bind_events(self) -> None:
        root = self._root
        root.bind("<Motion>", self._on_motion)
        root.bind("<Button-1>", self._on_press)
        root.bind("<B1-Motion>", self._on_drag_motion)
        root.bind("<ButtonRelease-1>", self._on_release)
        root.bind("<Button-3>", lambda _e: self._on_exit())

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
        self._drag = None

    # ---------- 渲染 ----------

    def render(self, light: Light) -> None:
        self._light = light
        self._paint()

    def tick_blink(self) -> None:
        if self._light is not Light.RED_BLINK:
            return
        self._blink_on = not self._blink_on
        self._paint()

    def _paint(self) -> None:
        if not self._hwnd:
            return
        lit = self._blink_on or self._light is not Light.RED_BLINK
        name = LIGHT_TO_FRAME[self._light] if lit else assets.DARK_FRAME
        frame = self._frames[name].resize((self._width, self._height()))
        layered.paint(self._hwnd, frame)

    def show(self) -> None:
        self._root.deiconify()
        self._paint()

    def hide(self) -> None:
        self._root.withdraw()
