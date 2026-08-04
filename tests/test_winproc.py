from tasklight.winproc import ProcRow, find_ancestor_pid, snapshot


def table(rows):
    return {r.pid: r for r in rows}


def test_沿父链找到目标进程():
    t = table([
        ProcRow(pid=100, ppid=50, name="python.exe"),
        ProcRow(pid=50, ppid=10, name="cmd.exe"),
        ProcRow(pid=10, ppid=1, name="claude.exe"),
    ])
    assert find_ancestor_pid(t, 100, "claude.exe") == 10


def test_自身即目标时返回自身():
    t = table([ProcRow(pid=10, ppid=1, name="claude.exe")])
    assert find_ancestor_pid(t, 10, "claude.exe") == 10


def test_链上没有目标时返回None():
    t = table([
        ProcRow(pid=100, ppid=50, name="python.exe"),
        ProcRow(pid=50, ppid=1, name="explorer.exe"),
    ])
    assert find_ancestor_pid(t, 100, "claude.exe") is None


def test_父链断裂时返回None():
    t = table([ProcRow(pid=100, ppid=999, name="python.exe")])
    assert find_ancestor_pid(t, 100, "claude.exe") is None


def test_超过深度上限即放弃():
    rows = [ProcRow(pid=i, ppid=i - 1, name="cmd.exe") for i in range(2, 20)]
    rows.append(ProcRow(pid=1, ppid=0, name="claude.exe"))
    assert find_ancestor_pid(table(rows), 19, "claude.exe", max_depth=3) is None


def test_自引用的进程不会死循环():
    t = table([ProcRow(pid=4, ppid=4, name="system")])
    assert find_ancestor_pid(t, 4, "claude.exe") is None


def test_真实快照能拿到当前进程():
    import os

    t = snapshot()
    assert os.getpid() in t
    assert t[os.getpid()].name.endswith(".exe")
