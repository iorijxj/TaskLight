"""设置窗口。托盘菜单打开，改完即时生效并落盘。"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from .config import MAX_INTERVAL_MS, MIN_INTERVAL_MS, Config

STEP_MS = 50
PAD = 10


class SettingsWindow:
    """同一时刻只允许开一个；重复调用会把已开的那个提到最前。"""

    def __init__(self, parent: tk.Tk, config: Config, on_apply: Callable[[Config], None]):
        self._parent = parent
        self._on_apply = on_apply
        self._window: tk.Toplevel | None = None
        self._config = config

    def open(self, config: Config) -> None:
        self._config = config
        if self._window is not None and self._window.winfo_exists():
            self._window.lift()
            self._window.focus_force()
            return
        self._build(config)

    def _build(self, config: Config) -> None:
        window = tk.Toplevel(self._parent)
        self._window = window
        window.title("TaskLight 设置")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        window.protocol("WM_DELETE_WINDOW", self._close)

        frame = ttk.Frame(window, padding=PAD)
        frame.grid(sticky="nsew")

        self._busy = tk.BooleanVar(value=config.blink_busy)
        self._background = tk.BooleanVar(value=config.blink_background)
        self._normal = tk.IntVar(value=config.blink_normal_ms)
        self._fast = tk.IntVar(value=config.blink_fast_ms)

        ttk.Label(frame, text="哪些状态闪烁", font=("Microsoft YaHei UI", 9, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Checkbutton(frame, text="忙碌（红灯）", variable=self._busy).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=2
        )
        ttk.Checkbutton(frame, text="后台运行（橙灯）", variable=self._background).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=2
        )
        ttk.Label(frame, text="等待确认（红+橙）始终闪烁，不可关闭", foreground="#888").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(0, PAD)
        )

        ttk.Label(frame, text="闪烁间隔", font=("Microsoft YaHei UI", 9, "bold")).grid(
            row=4, column=0, columnspan=2, sticky="w"
        )
        self._add_slider(frame, 5, "常规", self._normal)
        self._add_slider(frame, 6, "等待确认", self._fast)
        for var in (self._busy, self._background):
            var.trace_add("write", lambda *_: self._apply())

        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=2, sticky="e", pady=(PAD, 0))
        ttk.Button(buttons, text="恢复默认", command=self._reset).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="关闭", command=self._close).grid(row=0, column=1)

        self._center_on_parent(window)

    def _add_slider(self, frame: ttk.Frame, row: int, label: str, var: tk.IntVar) -> None:
        ttk.Label(frame, text=f"{label}：").grid(row=row, column=0, sticky="w")
        holder = ttk.Frame(frame)
        holder.grid(row=row, column=1, sticky="w")
        value_label = ttk.Label(holder, text=f"{var.get()} ms", width=8)

        def on_change(_value) -> None:
            snapped = round(var.get() / STEP_MS) * STEP_MS
            if snapped != var.get():
                var.set(snapped)
            value_label.configure(text=f"{snapped} ms")
            self._apply()

        scale = ttk.Scale(
            holder,
            from_=MIN_INTERVAL_MS,
            to=MAX_INTERVAL_MS,
            variable=var,
            command=on_change,
            length=200,
        )
        scale.grid(row=0, column=0)
        value_label.grid(row=0, column=1, padx=(6, 0))

    def _current(self) -> Config:
        return Config(
            blink_normal_ms=int(self._normal.get()),
            blink_fast_ms=int(self._fast.get()),
            blink_busy=bool(self._busy.get()),
            blink_background=bool(self._background.get()),
        )

    def _apply(self) -> None:
        self._config = self._current()
        self._on_apply(self._config)

    def _reset(self) -> None:
        defaults = Config()
        self._normal.set(defaults.blink_normal_ms)
        self._fast.set(defaults.blink_fast_ms)
        self._busy.set(defaults.blink_busy)
        self._background.set(defaults.blink_background)
        self._apply()

    def _close(self) -> None:
        if self._window is not None:
            self._window.destroy()
            self._window = None

    def _center_on_parent(self, window: tk.Toplevel) -> None:
        window.update_idletasks()
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        x = (screen_w - window.winfo_width()) // 2
        y = (screen_h - window.winfo_height()) // 2
        window.geometry(f"+{x}+{y}")
