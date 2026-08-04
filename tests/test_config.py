from tasklight import config as cfg


def test_默认值合理():
    c = cfg.Config()
    assert c.blink_fast_ms < c.blink_normal_ms
    assert c.blink_busy and c.blink_background


def test_往返读写(tmp_path):
    c = cfg.Config(blink_normal_ms=800, blink_fast_ms=150, blink_busy=False)
    cfg.save(tmp_path, c)
    assert cfg.load(tmp_path) == c


def test_没有配置文件时用默认值(tmp_path):
    assert cfg.load(tmp_path) == cfg.Config()


def test_配置文件损坏时用默认值(tmp_path):
    (tmp_path / cfg.CONFIG_FILE).write_text("{ 不是 json", encoding="utf-8")
    assert cfg.load(tmp_path) == cfg.Config()


def test_间隔过小被夹到下限():
    assert cfg.from_dict({"blink_normal_ms": 1}).blink_normal_ms == cfg.MIN_INTERVAL_MS


def test_间隔过大被夹到上限():
    assert cfg.from_dict({"blink_normal_ms": 999999}).blink_normal_ms == cfg.MAX_INTERVAL_MS


def test_间隔是非数字时退回默认():
    """配置文件用户可手改，坏值不能让程序崩。"""
    assert cfg.from_dict({"blink_fast_ms": "快一点"}).blink_fast_ms == cfg.Config().blink_fast_ms


def test_缺字段时逐项退回默认():
    c = cfg.from_dict({"blink_busy": False})
    assert c.blink_busy is False
    assert c.blink_normal_ms == cfg.Config().blink_normal_ms


def test_传入非字典时退回默认():
    assert cfg.from_dict([1, 2, 3]) == cfg.Config()


def test_不残留临时文件(tmp_path):
    cfg.save(tmp_path, cfg.Config())
    assert list(tmp_path.glob("*.tmp")) == []
