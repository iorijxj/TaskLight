import json
import time

from tasklight import store
from tasklight.state import SESSION_BUSY, SESSION_IDLE


def test_清洗非法字符():
    assert store.sanitize_id("a/../b c") == "a____b_c"


def test_清洗空值给出兜底名():
    assert store.sanitize_id("") == "unknown"


def test_写槽位后能读回(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY, cwd="E:\\p")
    slots = store.read_slots(tmp_path, now=time.time())
    assert len(slots) == 1
    assert slots[0].session_id == "sess-1"
    assert slots[0].state == SESSION_BUSY
    assert slots[0].cwd == "E:\\p"


def test_二次写入合并而非覆盖(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY, cwd="E:\\p")
    store.write_slot(tmp_path, "sess-1", bg_count=2)
    slot = store.read_slots(tmp_path, now=time.time())[0]
    assert slot.cwd == "E:\\p"
    assert slot.state == SESSION_BUSY
    assert slot.bg_count == 2


def test_缺bg_count字段时按零读(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY)
    assert store.read_slots(tmp_path, now=time.time())[0].bg_count == 0


def test_陈旧槽位被丢弃(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY)
    future = time.time() + store.STALE_SECONDS + 1
    assert store.read_slots(tmp_path, now=future) == []


def test_标记增删反映在计数上(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_IDLE)
    store.mark_add(tmp_path, "agents", "sess-1", "sub_1")
    store.mark_add(tmp_path, "agents", "sess-1", "sub_2")
    store.mark_add(tmp_path, "tasks", "sess-1", "task_1")
    slot = store.read_slots(tmp_path, now=time.time())[0]
    assert slot.pending_agents == 2
    assert slot.pending_tasks == 1

    store.mark_remove(tmp_path, "agents", "sess-1", "sub_1")
    slot = store.read_slots(tmp_path, now=time.time())[0]
    assert slot.pending_agents == 1


def test_重复删除标记不报错(tmp_path):
    store.mark_remove(tmp_path, "agents", "sess-1", "never_existed")


def test_删除会话连带清掉标记(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_IDLE)
    store.mark_add(tmp_path, "agents", "sess-1", "sub_1")
    store.drop_session(tmp_path, "sess-1")
    assert store.read_slots(tmp_path, now=time.time()) == []
    assert not (tmp_path / "agents" / "sess-1").exists()


def test_清理无主标记目录(tmp_path):
    store.mark_add(tmp_path, "agents", "ghost", "sub_1")
    store.prune_orphans(tmp_path, now=time.time())
    assert not (tmp_path / "agents" / "ghost").exists()


def test_清理超时标记文件(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_IDLE)
    store.mark_add(tmp_path, "agents", "sess-1", "sub_1")
    store.prune_orphans(tmp_path, now=time.time() + store.STALE_SECONDS + 1)
    assert not (tmp_path / "agents" / "sess-1" / "sub_1").exists()


def test_清空全部(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY)
    store.mark_add(tmp_path, "agents", "sess-1", "sub_1")
    store.clear_all(tmp_path)
    assert store.read_slots(tmp_path, now=time.time()) == []


def test_损坏的槽位文件被跳过而不崩(tmp_path):
    store.write_slot(tmp_path, "good", state=SESSION_BUSY)
    (tmp_path / "sessions" / "broken.json").write_text("{ 不是 json", encoding="utf-8")
    slots = store.read_slots(tmp_path, now=time.time())
    assert [s.session_id for s in slots] == ["good"]


def test_槽位文件写的是合法json(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY)
    raw = (tmp_path / "sessions" / "sess-1.json").read_text(encoding="utf-8")
    assert json.loads(raw)["state"] == SESSION_BUSY


def test_不残留临时文件(tmp_path):
    store.write_slot(tmp_path, "sess-1", state=SESSION_BUSY)
    assert list((tmp_path / "sessions").glob("*.tmp")) == []
