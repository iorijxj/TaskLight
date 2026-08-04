from tasklight.winproc import ProcRow, any_claude_alive, snapshot


def table(rows):
    return {r.pid: r for r in rows}


def test_检测到claude存活():
    t = table([
        ProcRow(pid=10, ppid=1, name="claude.exe"),
        ProcRow(pid=20, ppid=10, name="cmd.exe"),
    ])
    assert any_claude_alive(t) is True


def test_没有claude时为假():
    t = table([ProcRow(pid=1, ppid=0, name="explorer.exe")])
    assert any_claude_alive(t) is False


def test_空进程表为假():
    assert any_claude_alive({}) is False


def test_真实快照能拿到当前进程():
    import os

    t = snapshot()
    assert os.getpid() in t
    assert t[os.getpid()].name.endswith(".exe")
