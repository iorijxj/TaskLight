# TaskLight 设计文档

**日期**：2026-08-04
**目标**：Windows 桌面红绿灯，实时反映所有 Claude Code 会话的忙闲状态。

---

## 1. 需求

一个常驻桌面的红绿灯，让你余光一扫就知道该不该回去看屏幕。

| 灯 | 含义 |
|---|---|
| 🔴 闪烁 | Claude 停下来等你批准权限 —— 你不回去它就一直卡着 |
| 🔴 常亮 | Claude 正在干活，你可以走开 |
| 🟠 常亮 | 前台都停了，但后台子 Agent / Task / Bash 命令还在跑 |
| 🟢 常亮 | 全部完成，待机 |

### 已确定的决策

- **全局单灯**，不区分窗口，优先级 `waiting > busy > 后台 > 空闲` 短路聚合
- **形态**：置顶悬浮窗 + 系统托盘图标双管，两者颜色同步
- **启动**：手动双击 `start.cmd`，托盘右键退出。不做开机自启、不做自动拉起
- **监控范围**：CLI 会话与 VS Code 扩展会话一并纳入
- **橙灯覆盖三类后台活**：后台 Bash 命令、后台子 Agent / Task、其他窗口的未完成工作

### 非目标

- 不显示工具级细节（"正在编辑 X"）—— 三色够用，且能避开高频 hook
- 不做用量 / 配额 / 成本监控 —— 已有成熟项目（见附录）
- 不做远程会话（SSH / WSL）监控
- 不做 GUI 自动化测试

---

## 2. 技术背景（实地核查结论）

设计前对本机环境做了核查，三条结论直接决定了架构：

### 2.1 后台 Bash 完成时没有 hook 事件

`run_in_background: true` 的 Bash 启动时触发 `PostToolUse`，**结束时不触发任何 hook**。官方曾有 [issue #45781](https://github.com/anthropics/claude-code/issues/45781) 请求 `BackgroundTasksIdle` 事件，已 closed as not planned。因此后台 Bash 的结束只能靠外部探测。

`~\.claude\` 下也没有后台 Bash 的状态落盘：`daemon/roster.json` 记的是 FleetView 后台**会话**（pid / sessionId / cwd），`daemon/pty-pids` 同理，都与后台 Bash 无关。

### 2.2 进程树无法区分 MCP 与后台 Bash

本机实测每个 `claude.exe` 的子进程树：

```
claude.exe
  ├─ cmd.exe → npx @playwright/mcp        MCP，常驻
  ├─ mcp-server-windows-x64.exe (pencil)  MCP，常驻
  │   └─ node.exe → playwright-mcp
  │       └─ chrome.exe × 14              Chrome 整棵树
  └─ pwsh.exe -NoProfile -Command ...     工具执行的命令
```

MCP server 与工具执行的 shell 在进程树上**完全同形**（都是 `claude.exe` 经 `cmd.exe` 派生），靠树形状区分不了。若采用"idle 时有存活子进程即视为后台任务"，在本机会恒为真，橙灯常亮、绿灯永不出现。

**破局点**：`Win32_Process.CreationDate`。MCP 创建于会话启动时，后台 Bash 创建于某个已知时刻 —— 在时间轴上泾渭分明。

### 2.3 VS Code 扩展与 CLI 同引擎

扩展 `anthropic.claude-code-2.1.220-win32-x64` 目录下有 `resources\native-binary\claude.exe`，即扩展跑的是同一个 CLI 引擎，只是可执行文件路径不同。因此：

- hooks 读同一份 `~\.claude\settings.json`，装一次全覆盖，无需特殊处理
- 进程探测按**进程名** `claude.exe` 匹配（而非路径），扩展会话自动纳入

---

## 3. 架构

### 3.1 通信机制：每会话状态文件 + 轮询

Hook 脚本把状态写成幂等快照，GUI 每 400ms 扫目录聚合。

选它而不是本地 socket，是因为实时性对余光扫视场景无价值，却要换来一堆连接管理，且 GUI 未启动时 hook 会连接失败；选它而不是事件日志重放，是因为快照天然幂等，不必处理漏事件、乱序和日志轮转。

附带收益：槽位是快照而非累积状态，即便碰上 [issue #58637](https://github.com/anthropics/claude-code/issues/58637) 那种「僵尸 running 子代理」，最坏也只是橙灯多亮一会儿，不会永久卡红。

### 3.2 目录布局

```
E:\Github\TaskLight\
├─ tasklight\
│   ├─ state.py     纯函数：槽位 + 探测结果 → 灯色。无 I/O，全部可单测
│   ├─ store.py     槽位目录读写与陈旧清理
│   ├─ probe.py     后台进程探测（WMI + 创建时间过滤）
│   ├─ widget.py    tkinter 置顶悬浮窗
│   └─ tray.py      pystray 托盘图标
├─ hooks\
│   └─ tasklight_hook.py    唯一的 hook 脚本，靠 hook_event_name 分派
├─ main.py          组装：轮询循环 + widget + tray
├─ start.cmd        双击启动
├─ install_hooks.py 幂等合并 hooks 进 ~\.claude\settings.json
├─ docs\
└─ tests\
```

判定与采集/渲染彻底分离：`state.py` 只做纯计算，签名 `resolve(slots, probe_result) -> Light`，灯色的所有分支都能脱离 GUI 与 Claude Code 单测。

### 3.3 状态槽位

```
~\.claude\tasklight\
    sessions\<session_id>.json
    agents\<session_id>\<agent_id>      两级目录
    tasks\<session_id>\<task_id>
```

```json
{
  "session_id": "de0003c3-538a-4f5a-9804-644731157ab2",
  "state": "busy",
  "cwd": "E:\\Github\\TaskLight",
  "bg_since": 1785814071.5,
  "claude_pid": 11968,
  "updated_at": 1785814080.2
}
```

- `state` ∈ `idle | busy | waiting`
- `bg_since`：最近一次起后台 Bash 的时刻（epoch 秒）；`null` 表示该会话从未起过，探测阶段直接跳过
- `claude_pid`：该会话所属 `claude.exe` 的 PID，仅在写 `bg_since` 时一并解析并记录
- `cwd`：仅用于托盘 tooltip 显示哪个项目在忙

**为什么需要 `claude_pid`**：探测必须按会话隔离。若会话 A 的 `bg_since` 较早，而会话 B 是之后新开的窗口，B 的 MCP 进程创建时间会晚于 A 的 `bg_since` —— 不按 PID 归属就会把 B 的 MCP 误判为 A 的后台任务。

PID 的解析方式：hook 从自身 `os.getpid()` 沿父进程链向上找，遇到 `claude.exe` 即为所求，最多走 6 层。用 `ctypes` 调 `CreateToolhelp32Snapshot` 遍历进程表（标准库，约 10–20ms），**仅在 `PostToolUse(Bash, run_in_background)` 这一个低频分支执行**，其余事件不查进程。

**子 Agent / Task 用文件存在性代替计数器**：并行派多个 Agent 时 `SubagentStart` 会并发触发，读-改-写共享 JSON 必然丢更新、必须上锁；改为一个 Agent 一个空文件（`SubagentStart` 建、`SubagentStop` 删），天然无竞争、无锁、幂等。

用两级目录而非 `<session_id>__<agent_id>` 拼名，是因为 id 中可能含分隔符导致解析歧义；两级目录还让 `SessionEnd` 的级联清理变成一次 `rmtree`。

会话主状态文件只由主会话的串行事件写，用「写临时文件 + `os.replace`」原子覆写。

**输入清洗**：`session_id` / `agent_id` / `task_id` 来自 hook payload，属外部输入，用作路径前统一 `[^A-Za-z0-9_-] → _`，防路径穿越。

### 3.4 Hook 映射

| 事件 | matcher | 动作 | 频率 |
|---|---|---|---|
| `SessionStart` | — | 建槽位，`state=idle` | 低 |
| `UserPromptSubmit` | — | `state=busy` | 低 |
| `Notification` | `permission_prompt` | `state=waiting` | 低 |
| `Stop` / `StopFailure` | — | `state=idle` | 低 |
| `SubagentStart` | — | 建 `agents\<sid>\<aid>` | 低 |
| `SubagentStop` | — | 删 `agents\<sid>\<aid>` | 低 |
| `TaskCreated` | — | 建 `tasks\<sid>\<tid>` | 低 |
| `TaskCompleted` | — | 删 `tasks\<sid>\<tid>` | 低 |
| `SessionEnd` | — | 删槽位及名下 agent/task 目录 | 低 |
| `PostToolUse` | `Bash` | 若 `tool_input.run_in_background` 为真则写 `bg_since` | 中 |

**刻意不用 `PreToolUse`**：参考项目挂它是为显示工具级细节；只要三色的话，「前台忙」只需每轮一次的 `UserPromptSubmit` → `Stop`。这点很关键 —— Windows 上每个 hook 都要冷启动一个进程，挂在 `PreToolUse` 上会实打实拖慢 Claude Code。

唯一的中频 hook 是 `PostToolUse(Bash)`，脚本进去先看 `run_in_background`，不是就立刻退出。

所有事件共用一个 `tasklight_hook.py`，只 import `os / sys / json`，不碰第三方库，冷启动约 50ms。

### 3.5 灯色判定

优先级从上往下短路：

```
1. 任一槽位 state == waiting          → 🔴 闪烁（500ms 明暗切换）
2. 任一槽位 state == busy             → 🔴 常亮
3. 任一 agents\ 或 tasks\ 标记存在     → 🟠 常亮
4. 进程探测命中                        → 🟠 常亮
5. 否则                               → 🟢 常亮
```

`waiting` 排在 `busy` 之前，因为它是唯一需要你立刻行动的状态。

### 3.6 后台 Bash 探测

进程扫描每 2 秒执行一次，**一次扫描同时服务两件事**：判定后台活动，以及校验 `claude.exe` 是否还活着（见 3.7）。

存活校验不能只在「灯色前三步全不成立」时才做 —— 会话在 `busy` 状态下被强杀时，判定第 2 步会短路返回红灯，永远走不到探测，红灯就此卡死。因此扫描按固定间隔无条件执行（无槽位时跳过），代价约 1% CPU。

```
对每个 bg_since 非 null 的槽位：
    候选进程 = 该槽位 claude_pid 的所有后代
    命中条件 = 进程创建时间 >= bg_since - 2s
```

槽位中没有任何 `bg_since` 时，跳过后代枚举，只做存活校验。

`bg_since` 为 `null` 的会话根本不进探测，从源头杜绝假橙。MCP 与 Chrome 创建于会话启动时，远早于 `bg_since`，自动排除。`claude_pid` 使用前先校验该 PID 当前确实是 `claude.exe`，防 PID 复用。

**实现用 Win32 API 而非 WMI**：`CreateToolhelp32Snapshot` 拿全量 `(pid, ppid, name)`，再对候选进程逐个 `OpenProcess` + `GetProcessTimes` 取创建时间（`FILETIME` 转 epoch：`ticks / 1e7 - 11644473600`）。全程 ctypes 标准库，耗时 <20ms，远快于 WMI 的 100–300ms，也不必启动 PowerShell 子进程。

进程表获取与过滤逻辑分离 —— `has_background_activity(table, created_at, marks)` 的 `table` 和 `created_at` 均为可注入参数，让最易出错的时间戳判定能脱离真实系统单测。

### 3.7 僵尸槽位清理

三条兜底：

1. 系统中一个 `claude.exe` 都没有 → 清空全部槽位与全部 agent/task 标记（覆盖 Claude 整体崩溃 / 被强杀）。由 3.6 的 2 秒扫描承担，因此**无论当前灯色是什么都会执行**，最坏 2 秒内转绿
2. 槽位 `updated_at` 超过 4 小时未更新 → 丢弃（覆盖单会话异常终止）
3. **孤儿标记清理**：`agents\<sid>\` 或 `tasks\<sid>\` 对应的会话槽位已不存在 → 整目录删除；单个标记文件 mtime 超过 4 小时 → 删除

第 3 条是必需的，不是锦上添花：`SessionEnd` 是 agent/task 标记的唯一常规清理入口，一旦 `SubagentStop` 漏触发（见 issue #58637）又没走到 `SessionEnd`，残留标记会让橙灯永久亮着。

### 3.8 线程模型

改用 Win32 API 后探测耗时降到 <20ms，因此**不需要工作线程**：

```
主线程    tkinter mainloop
            └─ after(400ms)：读槽位 → 每 2 秒同步扫一次进程 → 算灯色 → 重绘
托盘线程  pystray icon.run_detached()
```

20ms 落在 400ms 的 tick 里对 UI 完全无感，省掉了工作线程、队列和「消费上一次快照」的延迟。扫描按 2 秒节流，所以五个 tick 里只有一个花这 20ms。

唯一的跨线程点是 pystray 托盘：它在自己的线程里跑消息循环，回调（显示/隐藏/退出）通过 `root.after(0, ...)` 转回主线程执行，不直接碰 tkinter 对象。

### 3.9 渲染

- **悬浮窗**：tkinter，`overrideredirect(True)` 去边框、`-topmost` 置顶、`-transparentcolor` 抠圆角、左键拖拽、不占任务栏。三个圆灯 + 底部状态文字
- **托盘**：pystray + Pillow 动态生成圆点图标，颜色与悬浮窗同步。右键菜单「显示/隐藏悬浮窗 · 退出」，tooltip 显示聚合摘要（如 `忙碌 · 2 会话 · 后台 1`）

依赖：`pystray`、`Pillow`。tkinter 随 Python 3.13.2 自带，已确认可用。`start.cmd` 用 `pythonw` 启动，避免残留一个黑色控制台窗口。

---

## 4. 错误处理

**红绿灯坏掉绝不能拖累写代码**，因此 hook 侧全程静默失败：顶层 `try/except` 包住一切，任何异常都 `exit 0`，仅在设了 `TASKLIGHT_DEBUG` 环境变量时向 `hook.log` 写一行。

GUI 侧：

- 单个槽位文件损坏 → 跳过该文件，不影响其余
- Win32 进程调用失败（快照句柄拿不到、`OpenProcess` 被拒）→ 探测降级为恒 `False`，灯照常工作，仅丢失后台 Bash 一档
- 槽位目录不存在 → 自动创建

`install_hooks.py` 要修改全局 `settings.json`（其中已有 `verify-write-fresh` 的 `PostToolUse` 条目），因此：写前自动备份 `.bak`、深度合并只追加不覆盖、幂等（重复运行不重复添加）、打印 diff 供确认。

---

## 5. 测试策略

按 `testing.md` 裁剪，重点压在纯逻辑：

| 模块 | 测法 |
|---|---|
| `state.py` | 全分支：waiting 压过 busy、busy 压过 agents、探测命中、全空、过期槽位被丢弃 |
| `store.py` | `tmp_path` 造假槽位目录，测读取 / 原子写 / 陈旧清理 / id 清洗 |
| `hooks` | 各事件 payload 喂 stdin，断言落盘结果；畸形 payload 必须 `exit 0` |
| `probe.py` | 注入假进程表，测创建时间过滤与 MCP 排除 |
| GUI | 手动验证，不写自动化测试 |

---

## 6. 待验证假设

以下三条以文档和推断为依据，尚未实测。实现第一步是装一个只做 payload dump 的临时 hook，跑一遍全场景拿真实数据，再据此动代码。

1. **`SubagentStart` / `SubagentStop` 的 `session_id` 归属**：是主会话的还是子代理自己的？文档只说"当前会话标识符"。若是子代理自己的，`agents\<session_id>\` 的归属和 `SessionEnd` 的级联清理需改用其他键关联。
2. **VS Code 扩展是否触发 hooks**：同引擎同配置，理论上必然触发，但未实测。验证方式：开一个扩展会话，看 `sessions\` 目录是否生成文件。
3. **后台 Bash 的 `PostToolUse` payload 形态**：需确认 `tool_input.run_in_background` 字段确实存在，以及 `tool_response` 中是否另有可用信息（若含 PID 等，探测可进一步简化）。

---

## 7. 实现顺序

1. 验证第 6 节的三条假设（临时 dump hook）
2. `state.py` + 测试（纯逻辑，先钉死）
3. `store.py` + `tasklight_hook.py` + 测试
4. `probe.py` + 测试
5. GUI：悬浮窗 → 托盘
6. `install_hooks.py` + 端到端手动验证

---

## 附录：调研过的同类项目

| 项目 | 平台 | 借鉴点 |
|---|---|---|
| [weilizhe8-del/claude-code-traffic-light](https://github.com/weilizhe8-del/claude-code-traffic-light) | Windows | 最接近的参考：tkinter 悬浮窗 + PID 分槽 + 多窗口聚合。三色语义不同（红=等权限/黄=运行/绿=完成），且用了高频 hook 与 PowerShell 脚本 |
| [eternityspring/agent-light](https://github.com/eternityspring/agent-light) | mac/Linux | Rust + eframe 置顶 GUI，另有 Arduino 实体灯后端 |
| [m1ckc3s/claude-status-bar](https://github.com/m1ckc3s/claude-status-bar) | macOS | 安装器自动合并 hooks 进 `~/.claude/settings.json` |
| [sr-kai/claudeusagewin](https://github.com/sr-kai/claudeusagewin) | Windows | C#/.NET 托盘、动态 SVG 图标、远程会话中继 |
| [fengyiqicoder/Lights](https://github.com/fengyiqicoder/Lights) | macOS | 同时支持 Claude Code + Codex CLI |
| [starlight36/vibecoding-signal-light](https://github.com/starlight36/vibecoding-signal-light) | 硬件 | 实体信号灯 |

均未实现「后台任务仍在跑」这一档 —— 这是本项目要自己解决的部分。
