"""置顶悬浮窗。透明抠色实现圆角，左键拖拽移动。"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from .state import LIGHT_LABELS, Light

WIDTH, HEIGHT = 56, 196
RADIUS = 17
CHROMA = "#ff00ff"
PANEL = "#101010"
TEXT_COLOR = "#d8d8d8"
BLINK_MS = 500
MARGIN_RIGHT = 24

BRIGHT = {"red": "#ff2a2a", "orange": "#ff9500", "green": "#22c55e"}
DIM = {"red": "#3d0000", "orange": "#3d2400", "green": "#052616"}
LIGHT_TO_LAMP = {
    Light.RED_BLINK: "red",
    Light.RED: "red",
    Light.ORANGE: "orange",
    Light.GREEN: "green",
}
LAMP_ORDER = ("red", "orange", "green")


class TrafficLightWidget:
    def __init__(self, root: tk.Tk, on_exit: Callable[[], None]):
        self._root = root
        self._on_exit = on_exit
        self._light = Light.GREEN
        self._blink_on = True
        self._drag_origin = (0, 0)
        self._build()

    def _build(self) -> None:
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-transparentcolor", CHROMA)
        self._root.configure(bg=CHROMA)
        self._place_at_right_edge()

        self._canvas = tk.Canvas(
            self._root, width=WIDTH, height=HEIGHT, bg=CHROMA, highlightthickness=0
        )
        self._canvas.pack()
        self._draw_panel()
        self._lamps = {name: self._draw_lamp(i, name) for i, name in enumerate(LAMP_ORDER)}
        self._label = self._canvas.create_text(
            WIDTH // 2, HEIGHT - 18, text="", fill=TEXT_COLOR, font=("Microsoft YaHei UI", 8)
        )
        self._bind_events()
        self.render(Light.GREEN)

    def _place_at_right_edge(self) -> None:
        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        x = screen_w - WIDTH - MARGIN_RIGHT
        y = (screen_h - HEIGHT) // 2
        self._root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    def _draw_panel(self) -> None:
        self._rounded_rect(0, 0, WIDTH, HEIGHT, 14, PANEL)

    def _rounded_rect(self, x1, y1, x2, y2, r, color) -> None:
        c = self._canvas
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color)
        c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline=color)
        for cx, cy in ((x1, y1), (x2 - 2 * r, y1), (x1, y2 - 2 * r), (x2 - 2 * r, y2 - 2 * r)):
            c.create_oval(cx, cy, cx + 2 * r, cy + 2 * r, fill=color, outline=color)

    def _draw_lamp(self, index: int, name: str) -> int:
        cx = WIDTH // 2
        cy = 30 + index * 48
        return self._canvas.create_oval(
            cx - RADIUS, cy - RADIUS, cx + RADIUS, cy + RADIUS, fill=DIM[name], outline=""
        )

    def _bind_events(self) -> None:
        self._canvas.bind("<Button-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<Button-3>", lambda _e: self._on_exit())

    def _on_press(self, event) -> None:
        self._drag_origin = (event.x, event.y)

    def _on_drag(self, event) -> None:
        dx = event.x - self._drag_origin[0]
        dy = event.y - self._drag_origin[1]
        self._root.geometry(f"+{self._root.winfo_x() + dx}+{self._root.winfo_y() + dy}")

    def render(self, light: Light) -> None:
        self._light = light
        self._paint()

    def tick_blink(self) -> None:
        if self._light is not Light.RED_BLINK:
            return
        self._blink_on = not self._blink_on
        self._paint()

    def _paint(self) -> None:
        active = LIGHT_TO_LAMP[self._light]
        lit = self._blink_on or self._light is not Light.RED_BLINK
        for name, item in self._lamps.items():
            on = name == active and lit
            self._canvas.itemconfigure(item, fill=BRIGHT[name] if on else DIM[name])
        self._canvas.itemconfigure(self._label, text=LIGHT_LABELS[self._light])

    def show(self) -> None:
        self._root.deiconify()

    def hide(self) -> None:
        self._root.withdraw()
