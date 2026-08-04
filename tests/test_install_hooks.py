import json
import sys
from pathlib import Path

from install_hooks import HOOK_ENTRIES, build_command, install, merge_hooks

COMMAND = build_command(Path("E:/Github/TaskLight/hooks/tasklight_hook.py"))


def test_命令行带S标志跳过site扫描(tmp_path):
    assert " -S " in build_command(tmp_path / "hooks" / "tasklight_hook.py")


def test_必须用解释器绝对路径而非裸python(tmp_path):
    """裸 `python` 会被 cmd.exe 按「当前目录优先」解析，而当前目录是用户打开的
    项目 —— 恶意仓库放个 python.exe 就能在 SessionStart 时拿到代码执行。"""
    command = build_command(tmp_path / "hooks" / "tasklight_hook.py")
    assert not command.startswith("python")
    assert Path(sys.executable).as_posix() in command


def test_解释器路径被引号包裹(tmp_path):
    """Python 常装在 C:\\Program Files 之类含空格的路径下。"""
    command = build_command(tmp_path / "hooks" / "tasklight_hook.py")
    assert command.startswith('"')


def test_空配置时装入全部事件():
    merged = merge_hooks({}, HOOK_ENTRIES, COMMAND)
    assert set(merged) == set(HOOK_ENTRIES)


def test_不碰他人已有的条目():
    """TaskLight 不再挂 PostToolUse，别人挂在上面的 hook 应原样保留。"""
    existing = {
        "PostToolUse": [
            {
                "matcher": "Write|Edit",
                "hooks": [{"type": "command", "command": "python other.py"}],
            }
        ]
    }
    merged = merge_hooks(existing, HOOK_ENTRIES, COMMAND)
    assert merged["PostToolUse"] == existing["PostToolUse"]


def test_与他人共用同一事件时追加而非替换():
    existing = {"Stop": [{"hooks": [{"type": "command", "command": "python other.py"}]}]}
    merged = merge_hooks(existing, HOOK_ENTRIES, COMMAND)
    commands = [h["command"] for entry in merged["Stop"] for h in entry["hooks"]]
    assert "python other.py" in commands
    assert COMMAND in commands


def test_不再挂载中频的PostToolUse():
    assert "PostToolUse" not in HOOK_ENTRIES


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


def test_升级时清掉命令已变的旧条目(tmp_path):
    """解释器路径变过一次（裸 python → 绝对路径）。若按完整命令匹配，
    旧条目清不掉，会新旧并存、hook 跑两遍，安全修复也就白做了。"""
    settings = tmp_path / "settings.json"
    hook = tmp_path / "hooks" / "tasklight_hook.py"
    legacy = f'python -S "{hook.as_posix()}"'
    settings.write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": legacy}]}]}}),
        encoding="utf-8",
    )
    install(settings, hook)

    data = json.loads(settings.read_text(encoding="utf-8"))
    commands = [h["command"] for e in data["hooks"]["Stop"] for h in e["hooks"]]
    assert legacy not in commands
    assert len(commands) == 1


def test_卸载能认出命令已变的旧条目(tmp_path):
    from install_hooks import uninstall

    settings = tmp_path / "settings.json"
    hook = tmp_path / "hooks" / "tasklight_hook.py"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {"hooks": [{"type": "command", "command": f'python -S "{hook.as_posix()}"'}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    assert uninstall(settings, hook) is True
    assert json.loads(settings.read_text(encoding="utf-8"))["hooks"] == {}


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


def test_写入是原子的不残留临时文件(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({}), encoding="utf-8")
    install(settings, tmp_path / "hooks" / "tasklight_hook.py")
    assert list(tmp_path.glob("*.tmp")) == []
    assert json.loads(settings.read_text(encoding="utf-8"))["hooks"]
