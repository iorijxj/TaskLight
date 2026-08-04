import json

from install_hooks import HOOK_ENTRIES, build_command, install, merge_hooks

COMMAND = 'python -S "E:/Github/TaskLight/hooks/tasklight_hook.py"'


def test_命令行带S标志跳过site扫描(tmp_path):
    command = build_command(tmp_path / "hooks" / "tasklight_hook.py")
    assert command.startswith("python -S ")


def test_空配置时装入全部事件():
    merged = merge_hooks({}, HOOK_ENTRIES, COMMAND)
    assert set(merged) == set(HOOK_ENTRIES)


def test_保留他人已有的条目():
    existing = {
        "PostToolUse": [
            {
                "matcher": "Write|Edit",
                "hooks": [{"type": "command", "command": "python other.py"}],
            }
        ]
    }
    merged = merge_hooks(existing, HOOK_ENTRIES, COMMAND)
    commands = [h["command"] for entry in merged["PostToolUse"] for h in entry["hooks"]]
    assert "python other.py" in commands
    assert COMMAND in commands


def test_重复执行不重复添加():
    once = merge_hooks({}, HOOK_ENTRIES, COMMAND)
    twice = merge_hooks(once, HOOK_ENTRIES, COMMAND)
    assert once == twice


def test_不修改传入的原配置():
    existing = {"PostToolUse": []}
    merge_hooks(existing, HOOK_ENTRIES, COMMAND)
    assert existing == {"PostToolUse": []}


def test_安装会写备份(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    install(settings, tmp_path / "hooks" / "tasklight_hook.py")
    assert (tmp_path / "settings.json.bak").exists()
    assert json.loads(settings.read_text(encoding="utf-8"))["model"] == "opus"


def test_二次安装不再改动(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({}), encoding="utf-8")
    hook = tmp_path / "hooks" / "tasklight_hook.py"
    assert install(settings, hook) is True
    assert install(settings, hook) is False


def test_安装后配置仍是合法json(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({}), encoding="utf-8")
    install(settings, tmp_path / "hooks" / "tasklight_hook.py")
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "SessionStart" in data["hooks"]


def test_卸载移除自身条目但保留他人(tmp_path):
    from install_hooks import uninstall

    settings = tmp_path / "settings.json"
    hook = tmp_path / "hooks" / "tasklight_hook.py"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "Write|Edit",
                            "hooks": [{"type": "command", "command": "python other.py"}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    install(settings, hook)
    assert uninstall(settings, hook) is True

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "SessionStart" not in data["hooks"]
    remaining = [h["command"] for e in data["hooks"]["PostToolUse"] for h in e["hooks"]]
    assert remaining == ["python other.py"]
