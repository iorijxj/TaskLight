# Hook Payload 实测结论

**日期**：2026-08-04　**环境**：Windows 11 / Claude Code 2.1.220 / Python 3.13.2

采样方式：临时挂 `dump_payload.py` 到各事件，跑真实交互会话（CLI + VS Code）。验证完临时 hook 已摘除。

---

## 结论一览

| 待验证假设 | 结论 |
|---|---|
| `SubagentStart.session_id` 是主会话还是子代理的？ | **主会话的**。设计中 `agents\<session_id>\<agent_id>` 的归属方式正确，无需修改 |
| VS Code 扩展会触发 hooks 吗？ | 未单独确证，但采样中出现多个不同 cwd 的会话，且扩展与 CLI 共用同一 `claude.exe` 引擎与同一份 settings.json |
| 后台 Bash 的 payload 形态？ | **发现了更好的东西 —— 见下** |

---

## 关键发现 1：`Stop` payload 直接给出后台任务列表

`Stop` 与 `SubagentStop` 的 payload 含 `background_tasks` 字段：

```json
"background_tasks": [
  {"id": "bebxmpum0", "type": "shell", "status": "running",
   "description": "起一个 5 分钟后台任务用于验证", "command": "python -c \"import time; time.sleep(300)\""}
],
"session_crons": []
```

- **每会话独立**：实测同一时刻，本会话为 `[{running}]`，另一会话为 `[]`
- 任务结束后的下一个 `Stop` 中该项消失
- 缺 `status` 字段的情况未观察到，代码按「运行中」保守处理

**影响**：整套「扫进程树 + 比对创建时间」的推断方案作废。删除 `probe.py`、`winproc` 的 `created_at`/`find_ancestor_pid`、槽位的 `bg_since`/`claude_pid`，以及唯一的中频 hook `PostToolUse(Bash)`。判定从推断变为事实。

---

## 关键发现 2：hook 读 stdin 必须自行按 UTF-8 解码

`sys.stdin.read()` 在 Windows 上用 locale 编码（cp936）解 UTF-8 的 payload，遇到解不了的字节产生 surrogate 字符，写文件时抛 `UnicodeEncodeError`。顶层 `try/except` 把它静默吞掉。

实测：5 个 payload 落盘，**4 个 0 字节**，唯一成功的 `SubagentStart` 恰好是纯 ASCII。

| payload 特征 | 结果 |
|---|---|
| `Stop`（含中文 `last_assistant_message`） | 崩 |
| `UserPromptSubmit`（含中文输入） | 崩 |
| `PostToolUse`（含中文 `description`） | 崩 |
| `SessionStart` / `SubagentStart` / `Notification`（纯 ASCII） | 正常 |

**后果**：中文对话下红绿灯完全失灵，且不报任何错——只有纯 ASCII 事件能落盘，灯只会亮不会灭。

**修复**：`sys.stdin.buffer.read().decode("utf-8", errors="replace")`。已加 3 项回归测试，用 UTF-8 字节流喂 stdin 复现真实场景。

---

## 排查过程中的两个假信号

记录下来，避免以后重蹈覆辙：

1. **`claude -p` 非交互模式不发后置 hook**。我最初用 `claude -p` 做实验，观察到 `Stop`/`PostToolUse`/`SubagentStop` 从不触发，据此得出「后置事件不可靠」的错误结论。交互式会话中这些事件一直正常。**测 hook 必须用交互式会话。**

2. **matcher 语义正常**。一度怀疑 `matcher: "Bash"` 不匹配，实测 `Bash` / `^Bash$` / `Bash.*` / `.*` / `^Bash` / `Write|Edit|Bash` 六种写法**全部命中**。当时的「不触发」实为上述编码 bug 所致。

---

## 其余确认

- `SubagentStart` 带 `agent_id`、`agent_type`（实测 `Explore`）
- `Notification` 的 `notification_type: "permission_prompt"` 工作正常，`message` 为 `"Claude needs your permission"`
- `Stop` 带 `stop_hook_active`、`permission_mode`、`effort`
- 直接编辑 settings.json 的 hooks 会被 file watcher 自动拾取，**不需要**在 `/hooks` 里确认；但已在运行的会话可能要等下一轮才生效
- `/hooks` 是只读的分层浏览器，需选中事件回车才能看到 handler 详情
