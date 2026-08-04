from tasklight.state import (
    Light,
    Slot,
    SESSION_BUSY,
    SESSION_IDLE,
    SESSION_WAITING,
    resolve,
    resolve_without_probe,
    summarize,
)


def slot(state=SESSION_IDLE, agents=0, tasks=0, bg_since=None):
    return Slot(
        session_id="s1",
        state=state,
        cwd="E:\\proj",
        bg_since=bg_since,
        claude_pid=None,
        updated_at=0.0,
        pending_agents=agents,
        pending_tasks=tasks,
    )


def test_waiting_压过_busy():
    slots = [slot(SESSION_BUSY), slot(SESSION_WAITING)]
    assert resolve_without_probe(slots) is Light.RED_BLINK


def test_busy_压过_未完成子agent():
    slots = [slot(SESSION_IDLE, agents=3), slot(SESSION_BUSY)]
    assert resolve_without_probe(slots) is Light.RED


def test_前台全停但有未完成子agent时为橙():
    assert resolve_without_probe([slot(SESSION_IDLE, agents=1)]) is Light.ORANGE


def test_前台全停但有未完成task时为橙():
    assert resolve_without_probe([slot(SESSION_IDLE, tasks=1)]) is Light.ORANGE


def test_全部空闲时需要探测才能定夺():
    assert resolve_without_probe([slot(SESSION_IDLE)]) is None


def test_无任何会话时需要探测才能定夺():
    assert resolve_without_probe([]) is None


def test_探测命中为橙():
    assert resolve([slot(SESSION_IDLE)], background_active=True) is Light.ORANGE


def test_探测未命中为绿():
    assert resolve([slot(SESSION_IDLE)], background_active=False) is Light.GREEN


def test_探测结果不影响已定夺的灯色():
    assert resolve([slot(SESSION_BUSY)], background_active=True) is Light.RED


def test_摘要含会话数与后台数():
    slots = [slot(SESSION_BUSY), slot(SESSION_IDLE, agents=2)]
    text = summarize(slots, Light.RED)
    assert "忙碌" in text and "1 会话" in text and "后台 2" in text


def test_待机摘要不带多余计数():
    assert summarize([slot(SESSION_IDLE)], Light.GREEN) == "待机"
