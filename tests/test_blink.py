"""闪烁引擎的纯逻辑测试：不起真窗口，替换掉绘制。"""
import tkinter as tk

import pytest

from tasklight.config import Config
from tasklight.state import Light
from tasklight.widget import TrafficLightWidget


@pytest.fixture(scope="module")
def tk_root():
    """整个模块共用一个 Tk：反复 Tk()+destroy() 会让 Tcl 解释器失效
    （报 invalid command name "tcl_findLibrary"）。"""
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def widget(tk_root, monkeypatch):
    # 别让测试读到真实的窗口位置配置
    monkeypatch.setattr("tasklight.store.load_window", lambda *_a, **_k: None)
    holder = tk.Toplevel(tk_root)
    w = TrafficLightWidget(holder, Config())
    w._hwnd = 0  # 让 _paint 直接返回，不碰 Win32
    yield w
    holder.destroy()


def phases(w, light, config, ticks, step):
    """按固定步长推进时间，采样亮灭序列。"""
    w.set_config(config)
    w._light = light
    w._lit = True
    w._last_flip = 0.0
    out = []
    for i in range(ticks):
        w.tick_blink(now=i * step)
        out.append(w._lit)
    return out


def test_等待确认始终闪且用快速间隔(widget):
    c = Config(blink_normal_ms=600, blink_fast_ms=200)
    widget._light = Light.WAITING
    widget.set_config(c)
    assert widget.blink_interval() == pytest.approx(0.2)


def test_等待确认无法被关闭(widget):
    """它是唯一「不回去就一直卡着」的状态，不给关。"""
    c = Config(blink_busy=False, blink_background=False)
    widget._light = Light.WAITING
    widget.set_config(c)
    assert widget.blink_interval() is not None


def test_忙碌按常规间隔闪(widget):
    widget._light = Light.BUSY
    widget.set_config(Config(blink_normal_ms=600))
    assert widget.blink_interval() == pytest.approx(0.6)


def test_关闭忙碌闪烁后常亮(widget):
    widget._light = Light.BUSY
    widget.set_config(Config(blink_busy=False))
    assert widget.blink_interval() is None


def test_关闭后台闪烁后常亮(widget):
    widget._light = Light.BACKGROUND
    widget.set_config(Config(blink_background=False))
    assert widget.blink_interval() is None


def test_待机永远常亮(widget):
    widget._light = Light.IDLE
    widget.set_config(Config())
    assert widget.blink_interval() is None


def test_按时间戳翻转而非按调用次数(widget):
    """采样粒度 50ms、间隔 200ms，应该每 4 次采样才翻一次。"""
    seq = phases(widget, Light.WAITING, Config(blink_fast_ms=200), ticks=9, step=0.05)
    assert seq == [True, True, True, True, False, False, False, False, True]


def test_快慢间隔产生不同频率(widget):
    fast = phases(widget, Light.WAITING, Config(blink_fast_ms=100), ticks=8, step=0.05)
    widget._light = Light.BUSY
    slow = phases(widget, Light.BUSY, Config(blink_normal_ms=400), ticks=8, step=0.05)
    assert fast.count(True) < slow.count(True)


def test_常亮状态下若处于熄灭会立刻点亮(widget):
    widget._light = Light.IDLE
    widget._lit = False
    widget.tick_blink(now=100.0)
    assert widget._lit is True


def test_切换灯色时重置为点亮(widget):
    widget._light = Light.WAITING
    widget._lit = False
    widget.render(Light.BUSY)
    assert widget._lit is True


def test_灯色未变时render不重绘(widget):
    widget._light = Light.BUSY
    widget._lit = False
    widget.render(Light.BUSY)
    assert widget._lit is False
