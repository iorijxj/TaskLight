from tasklight.state import (
    Light,
    Slot,
    SESSION_BUSY,
    SESSION_IDLE,
    SESSION_WAITING,
    resolve,
    summarize,
)


def slot(state=SESSION_IDLE, agents=0, tasks=0, bg=0):
    return Slot(
        session_id="s1",
        state=state,
        cwd="E:\\proj",
        bg_count=bg,
        updated_at=0.0,
        pending_agents=agents,
        pending_tasks=tasks,
    )


def test_waiting_压过_busy():
    assert resolve([slot(SESSION_BUSY), slot(SESSION_WAITING)]) is Light.WAITING


def test_busy_压过_未完成子agent():
    assert resolve([slot(SESSION_IDLE, agents=3), slot(SESSION_BUSY)]) is Light.BUSY


def test_busy_压过_后台任务():
    assert resolve([slot(SESSION_IDLE, bg=2), slot(SESSION_BUSY)]) is Light.BUSY


def test_前台全停但有未完成子agent时为橙():
    assert resolve([slot(SESSION_IDLE, agents=1)]) is Light.BACKGROUND


def test_前台全停但有未完成task时为橙():
    assert resolve([slot(SESSION_IDLE, tasks=1)]) is Light.BACKGROUND


def test_前台全停但有后台命令时为橙():
    assert resolve([slot(SESSION_IDLE, bg=1)]) is Light.BACKGROUND


def test_全部空闲为绿():
    assert resolve([slot(SESSION_IDLE)]) is Light.IDLE


def test_无任何会话为绿():
    assert resolve([]) is Light.IDLE


def test_其他会话的后台任务也算数():
    assert resolve([slot(SESSION_IDLE), slot(SESSION_IDLE, bg=1)]) is Light.BACKGROUND


def test_后台总数合并三个来源():
    assert slot(agents=2, tasks=1, bg=3).background_total == 6


def test_摘要含会话数与后台数():
    slots = [slot(SESSION_BUSY), slot(SESSION_IDLE, agents=2)]
    text = summarize(slots, Light.BUSY)
    assert "忙碌" in text and "1 会话" in text and "后台 2" in text


def test_摘要把后台命令计入总数():
    text = summarize([slot(SESSION_IDLE, bg=2, agents=1)], Light.BACKGROUND)
    assert "后台 3" in text


def test_待机摘要不带多余计数():
    assert summarize([slot(SESSION_IDLE)], Light.IDLE) == "待机"
