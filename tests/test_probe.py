from tasklight.probe import (
    any_claude_alive,
    descendants,
    has_background_activity,
    marks_from_slots,
)
from tasklight.state import SESSION_IDLE, Slot
from tasklight.winproc import ProcRow

CLAUDE = 100
BG_SINCE = 1000.0


def table(rows):
    return {r.pid: r for r in rows}


def base_table():
    return table([
        ProcRow(pid=CLAUDE, ppid=1, name="claude.exe"),
        ProcRow(pid=200, ppid=CLAUDE, name="cmd.exe"),
        ProcRow(pid=300, ppid=200, name="node.exe"),
    ])


def times(mapping):
    return lambda pid: mapping.get(pid)


def test_枚举后代含孙进程():
    assert descendants(base_table(), CLAUDE) == {200, 300}


def test_枚举后代不含自身():
    assert CLAUDE not in descendants(base_table(), CLAUDE)


def test_环形父子关系不会死循环():
    t = table([
        ProcRow(pid=1, ppid=2, name="a.exe"),
        ProcRow(pid=2, ppid=1, name="b.exe"),
    ])
    assert descendants(t, 1) == {2}


def test_mcp进程早于后台时刻不算命中():
    fn = times({200: BG_SINCE - 600, 300: BG_SINCE - 600})
    assert has_background_activity(base_table(), fn, [(CLAUDE, BG_SINCE)]) is False


def test_后台时刻之后创建的进程算命中():
    fn = times({200: BG_SINCE - 600, 300: BG_SINCE + 1})
    assert has_background_activity(base_table(), fn, [(CLAUDE, BG_SINCE)]) is True


def test_宽限期内略早的进程也算命中():
    fn = times({200: BG_SINCE - 1.0, 300: None})
    assert has_background_activity(base_table(), fn, [(CLAUDE, BG_SINCE)], grace=2.0) is True


def test_pid被复用为其他进程时跳过():
    t = table([
        ProcRow(pid=CLAUDE, ppid=1, name="chrome.exe"),
        ProcRow(pid=200, ppid=CLAUDE, name="cmd.exe"),
    ])
    fn = times({200: BG_SINCE + 10})
    assert has_background_activity(t, fn, [(CLAUDE, BG_SINCE)]) is False


def test_claude进程已消失时跳过():
    fn = times({200: BG_SINCE + 10})
    assert has_background_activity({}, fn, [(CLAUDE, BG_SINCE)]) is False


def test_无标记时直接为假():
    assert has_background_activity(base_table(), times({}), []) is False


def test_取不到创建时间的进程被忽略():
    assert has_background_activity(base_table(), times({}), [(CLAUDE, BG_SINCE)]) is False


def test_多会话中任一命中即为真():
    t = table([
        ProcRow(pid=CLAUDE, ppid=1, name="claude.exe"),
        ProcRow(pid=200, ppid=CLAUDE, name="cmd.exe"),
        ProcRow(pid=400, ppid=1, name="claude.exe"),
        ProcRow(pid=500, ppid=400, name="cmd.exe"),
    ])
    fn = times({200: BG_SINCE - 600, 500: BG_SINCE + 5})
    assert has_background_activity(t, fn, [(CLAUDE, BG_SINCE), (400, BG_SINCE)]) is True


def slot(pid, bg):
    return Slot(
        session_id="s",
        state=SESSION_IDLE,
        cwd="",
        bg_since=bg,
        claude_pid=pid,
        updated_at=0.0,
        pending_agents=0,
        pending_tasks=0,
    )


def test_只挑出有完整后台信息的槽位():
    slots = [slot(CLAUDE, BG_SINCE), slot(None, BG_SINCE), slot(CLAUDE, None)]
    assert marks_from_slots(slots) == [(CLAUDE, BG_SINCE)]


def test_检测claude是否存活():
    assert any_claude_alive(base_table()) is True
    assert any_claude_alive(table([ProcRow(pid=1, ppid=0, name="explorer.exe")])) is False
