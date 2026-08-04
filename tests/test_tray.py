from tasklight.state import Light
from tasklight.tray import TrayIcon


class FakeIcon:
    """替身：只记录赋值，模拟 pystray 未就绪时 visible=False 的行为。"""

    def __init__(self):
        self.visible = False
        self.icon = None
        self.title = None


def make_tray():
    tray = TrayIcon(on_toggle=lambda: None, on_settings=lambda: None, on_exit=lambda: None)
    tray._icon = FakeIcon()
    return tray


def test_托盘未就绪时不更新也不记录状态():
    tray = make_tray()
    tray.update(Light.BUSY, "忙碌")
    assert tray._icon.icon is None
    assert tray._light is None


def test_就绪后会补上之前跳过的更新():
    """启动竞态：第一次 tick 落在 visible=False 期间，若那时就记下状态，
    托盘会永远定格在初始图标。"""
    tray = make_tray()
    tray.update(Light.BUSY, "忙碌")
    tray._icon.visible = True
    tray.update(Light.BUSY, "忙碌")
    assert tray._icon.icon is not None
    assert tray._light is Light.BUSY


def test_灯色不变时不重建图标():
    tray = make_tray()
    tray._icon.visible = True
    tray.update(Light.BUSY, "忙碌 · 1 会话")
    first = tray._icon.icon
    tray.update(Light.BUSY, "忙碌 · 2 会话")
    assert tray._icon.icon is first
    assert tray._icon.title == "忙碌 · 2 会话"


def test_灯色变化时重建图标():
    tray = make_tray()
    tray._icon.visible = True
    tray.update(Light.BUSY, "忙碌")
    first = tray._icon.icon
    tray.update(Light.IDLE, "待机")
    assert tray._icon.icon is not first
    assert tray._light is Light.IDLE
