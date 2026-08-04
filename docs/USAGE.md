# TaskLight 使用文档

Windows 桌面红绿灯，用余光就能知道 Claude Code 在忙什么。

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [安装](#安装)
- [验证装好了](#验证装好了)
- [日常操作](#日常操作)
- [灯态规则](#灯态规则)
- [设置](#设置)
- [文件位置](#文件位置)
- [故障排查](#故障排查)
- [卸载](#卸载)
- [工作原理](#工作原理)

---

## 它解决什么问题

用 Claude Code 时最浪费时间的两件事：

1. **它停下来等你批准权限，你却在看别的窗口** —— 它就那么一直卡着
2. **它其实早干完了，你还以为在跑** —— 或者反过来，你以为完事了，后台任务还在跑

TaskLight 把这些状态变成桌面角落一盏灯。不用切窗口、不用盯屏幕，余光一扫就知道要不要回去。

它**聚合所有会话**：不管你开了几个 CLI 窗口、还是在 VS Code 扩展里，都汇总成一盏灯。

---

## 安装

### 前置条件

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11 |
| Python | 3.13 或更高，安装时勾选了 tkinter（标准安装包默认带） |
| Claude Code | 任意近期版本 |

检查 Python 和 tkinter：

```powershell
python --version
python -c "import tkinter; print('tkinter ok')"
```

### 第一步：装依赖

```powershell
cd E:\Github\TaskLight
python -m pip install -e .
```

装的是 `pystray`（托盘图标）和 `Pillow`（图像处理）。**hook 侧一个第三方库都不用**，只有界面程序需要。

### 第二步：装 hooks

```powershell
python install_hooks.py
```

这一步会往 `~\.claude\settings.json` 里合并 10 个 hook 事件。它的行为：

- **自动备份**到 `settings.json.bak`
- **幂等**：重复运行不会产生重复条目
- **不动你已有的 hook**：只追加自己的条目
- **自动清理旧版本**：升级时会先移除指向本项目的旧条目再装新的

输出会告诉你新增了哪些事件、备份在哪。

### 第三步：重启 Claude Code

**这一步不能省。** hook 配置在会话启动时读取，已经开着的窗口不会生效。

### 第四步：启动灯

双击 `start.cmd`。屏幕右侧中间会出现一个横置的红绿灯。

---

## 验证装好了

**看 hooks 是否加载**：在 Claude Code 里输入 `/hooks`。这是个分层浏览器，**要选中事件按回车**才能看到具体的 handler，直接看列表页是看不到条目内容的。

**看灯是否响应**：在任意 Claude Code 窗口发一句话，灯应该立刻变红。

**看槽位文件**：

```powershell
dir $env:USERPROFILE\.claude\tasklight\sessions
```

每个活跃会话对应一个 `<session_id>.json`。如果这个目录是空的，说明 hook 没触发，见[故障排查](#故障排查)。

---

## 日常操作

| 操作 | 效果 |
|---|---|
| 灯上**左键拖动** | 移动位置 |
| 拖**边缘或四角** | 等比缩放，宽度范围 180–960 像素 |
| 托盘图标**左键** | 显示 / 隐藏悬浮窗 |
| 托盘图标**右键 → 设置** | 调闪烁节奏与规则 |
| 托盘图标**右键 → 退出** | **唯一的退出入口** |

几个刻意的设计：

- **悬浮窗不响应右键。** 退出只走托盘 —— 在灯上误点一下就把它关了的代价太大，而退出本身是低频操作。
- **位置和尺寸会记住。** 拖动或缩放松手时就落盘（不是等退出才存，所以进程崩了也不丢）。换了显示器或改了分辨率导致旧位置落在屏幕外时，会自动回到默认位置。
- **重复双击 `start.cmd` 不会起出第二个实例**，会弹窗提示。

---

## 灯态规则

### 四种状态

| 灯 | 含义 | 默认表现 |
|---|---|---|
| 🔴🟠 **红+橙** | Claude 停下来等你**批准权限** | **快闪 250ms** |
| 🔴 红 | Claude 正在干活 | 慢闪 600ms |
| 🟠 橙 | 前台都停了，但后台还有活 | 慢闪 600ms |
| 🟢 绿 | 全部完成，待机 | 常亮 |

「后台还有活」指这三类之一：

- 后台 Bash 命令（`run_in_background`）还在跑
- 派出去的子 Agent 还没返回
- 创建的 Task 还没完成

### 多窗口怎么聚合

**按优先级取最紧急的那个**，不是按窗口数：

```
任一会话在等你批准    → 红+橙
否则任一会话在干活    → 红
否则任一会话有后台活  → 橙
否则                  → 绿
```

托盘悬停能看到摘要，比如 `忙碌 · 2 会话 · 后台 3`。

### 为什么只有「等待确认」默认快闪

闪烁是打断性最强的信号，用滥了就没用了。设计意图是：

- **闪烁 = 卡住了，你不回去它就一直等着**
- **常亮 = 机器在自己跑，你可以走开**

「等待确认」是唯一符合前者的状态，所以它永远闪、且闪得最快，**并且不允许在设置里关掉**。

---

## 设置

托盘右键 → **设置**。改动**即时生效并自动保存**，没有"保存"按钮。

| 项 | 范围 | 说明 |
|---|---|---|
| 忙碌（红灯）闪烁 | 开 / 关 | 关掉后忙碌时红灯常亮 |
| 后台运行（橙灯）闪烁 | 开 / 关 | 关掉后后台运行时橙灯常亮 |
| 常规间隔 | 100–3000ms | 忙碌和后台的闪烁节奏 |
| 等待确认间隔 | 100–3000ms | 红+橙齐闪的节奏 |

「恢复默认」按钮会重置这四项。

### 调参建议

- **觉得闪得晃眼**：关掉「忙碌闪烁」，只留后台和等待确认闪。这样你写代码时余光是安静的，只有真需要你时才动。
- **想要缓一点的呼吸感**：把常规间隔拖到 1500ms 以上。
- **完全不想被闪烁干扰**：两个开关都关掉。等待确认仍会快闪 —— 这是刻意的。

---

## 文件位置

```
~\.claude\tasklight\
├── config.json              闪烁设置（改过设置后才有）
├── window.json              悬浮窗位置与尺寸（拖动或缩放后才有）
├── sessions\<session_id>.json        每个会话的状态快照
├── agents\<session_id>\<agent_id>    未完成的子 Agent（派过子 Agent 后才有）
└── tasks\<session_id>\<task_id>      未完成的 Task（用过 TaskCreate 后才有）
```

**这些文件和目录都是按需创建的** —— 没用到对应功能就不存在，属正常现象。比如从没用过 `TaskCreate`，`tasks\` 目录就不会出现。

都可以随时删除，程序会在需要时重建。删 `config.json` 等于恢复默认设置，删 `window.json` 等于让窗口回到默认位置。

hook 配置写在 `~\.claude\settings.json`，备份在同目录的 `settings.json.bak`。

---

## 故障排查

### 灯一直是绿的，发消息也不变

**最常见原因：装完 hooks 后没重启 Claude Code。** hook 配置在会话启动时读取。

其次检查：

```powershell
# 1. hooks 装了吗
python -c "import json,pathlib; d=json.loads((pathlib.Path.home()/'.claude/settings.json').read_text(encoding='utf-8')); print([k for k,v in d.get('hooks',{}).items() for e in v for h in e.get('hooks',[]) if 'tasklight' in h.get('command','')])"

# 2. 槽位有没有生成
dir $env:USERPROFILE\.claude\tasklight\sessions
```

如果 hooks 列表是空的，重新跑 `python install_hooks.py`。

### 想看 hook 到底有没有报错

hook 默认全程静默失败 —— 它绝不能因为自己出错而拖累你写代码。要看错误，设置环境变量后重启 Claude Code：

```powershell
setx TASKLIGHT_DEBUG 1
```

之后错误会写进 `~\.claude\tasklight\hook.log`。排查完记得 `setx TASKLIGHT_DEBUG ""` 关掉。

### 托盘有个颜色不对的图标，怎么点都没反应

**这是僵尸图标** —— 进程被强制结束（任务管理器、`taskkill /F`）时，Windows 不会移除它的托盘图标，图标会定格在被杀那一刻的颜色。

**鼠标划过托盘区域，它就会消失。**

避免办法：用托盘菜单的「退出」正常关闭，不要强杀进程。

### 悬浮窗不见了

可能是托盘菜单里被隐藏了。**托盘图标左键单击**可以切回显示。

如果托盘图标也找不到：Win11 默认把新程序的托盘图标折叠进溢出区（任务栏那个 `^` 箭头），点开就能看到，可以拖出来固定。

### 灯卡在红色不动

正常情况下不会发生 —— 即使 Claude Code 崩溃或被强杀，灯也会在 2 秒内转绿（程序会检查 `claude.exe` 是否还存在，全没了就清空状态）。

如果真卡住了，删掉槽位目录即可：

```powershell
Remove-Item -Recurse -ErrorAction SilentlyContinue $env:USERPROFILE\.claude\tasklight\sessions
```

### 橙灯一直亮着不灭

可能是某个子 Agent 的结束事件漏触发了，残留了标记文件。有两道兜底：会话结束（`SessionEnd`）时清理，或标记文件超过 4 小时自动失效。

想立刻清掉（这两个目录可能只存在其中一个，`-ErrorAction SilentlyContinue` 用来忽略不存在的那个）：

```powershell
Remove-Item -Recurse -ErrorAction SilentlyContinue `
  $env:USERPROFILE\.claude\tasklight\agents, $env:USERPROFILE\.claude\tasklight\tasks
```

### 双击 start.cmd 弹窗说「已在运行」

说明已经有一个实例了。先试试托盘图标（可能折叠在任务栏溢出区里）。如果确实找不到，强制结束它：

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*main.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId }
```

用 `Get-CimInstance` 而不是 `Get-Process`，是因为后者的 `CommandLine` 属性只有 PowerShell 7 才有，在 Windows PowerShell 5.1 上会静默匹配不到任何进程。

**注意这是强制结束，会留下僵尸托盘图标**（鼠标划过即消失）。能用托盘菜单退出就别用这个。

### 多个用户同时登录（RDP / 快速用户切换）

每个登录会话可以各自运行一个 TaskLight，互不干扰。

---

## 卸载

```powershell
python install_hooks.py --uninstall
Remove-Item -Recurse $env:USERPROFILE\.claude\tasklight
```

第一条会精确移除本项目挂的 hook 条目（**按脚本路径识别，不会误删你自己的 hook**），第二条删掉状态和配置目录。

卸载后**重启 Claude Code** 让 hook 变更生效。

---

## 工作原理

```
Claude Code hooks ──写──► ~\.claude\tasklight\sessions\<session_id>.json
                                      │
                                      ▼  每 400ms 读取并聚合
                              悬浮窗 + 托盘图标
```

### 为什么这么设计

**全部用低频 hook。** 挂的 10 个事件（`SessionStart` / `UserPromptSubmit` / `Stop` / `Notification` / `SubagentStart|Stop` / `TaskCreated|Completed` / `SessionEnd` / `StopFailure`）都是每轮对话触发一次的。刻意不用 `PreToolUse` / `PostToolUse` —— Windows 上每次 hook 都要冷启动一个 Python 进程（约 100ms），挂在高频事件上会实打实拖慢 Claude Code。

**后台任务不靠推断。** `Stop` 事件的 payload 里直接带 `background_tasks` 列表（含每个任务的运行状态），这是 Claude Code 给出的事实，不需要去扫进程树猜。

**子 Agent 计数用「一个 ID 一个空文件」。** 并行派多个 Agent 时 `SubagentStart` 会并发触发，如果读-改-写同一个 JSON 必然丢更新；改成一个 Agent 一个空文件，天然无竞争、不需要加锁。

**透明用的是 Win32 分层窗口。** tkinter 的 Canvas 画 RGBA 图时，透明像素显示的是 Canvas 底色而不是桌面。改走 `UpdateLayeredWindow` 才能逐像素与桌面混合，让圆角和抗锯齿边缘正确过渡。

### 已知限制

- 灯每 400ms 刷新，崩溃兜底每 2 秒检查一次
- 仅支持 Windows（依赖 Win32 进程 API 和分层窗口）
- 不监控 SSH / WSL 上的远程会话
- hook 侧永远不能引入第三方库（命令行带 `-S` 跳过了 site-packages 扫描）
- 若 `SubagentStop` 漏触发，橙灯会多亮一会儿，靠 `SessionEnd` 或 4 小时超时兜底

### 性能

| 项 | 开销 |
|---|---|
| hook 冷启动 | 约 100ms，每轮对话两次 |
| GUI 轮询 | 每 400ms 读一次槽位，约 1ms |
| 进程快照 | 每 2 秒一次，446 个进程约 11ms |
| 灯重绘 | 约 3ms，仅在灯色变化或闪烁翻转时 |

hook 那 100ms 里有 49ms 是 Python 解释器自身启动，压不下去。已做的优化：命令行 `-S` 跳过 site 扫描（省 17ms）、延迟 import `shutil`（它连带 bz2/lzma，省 20ms）。

---

## 更多文档

- 设计决策与实测结论：`docs/superpowers/specs/`
- Hook payload 实测记录：`docs/hook-payload-findings.md`
- 实现计划：`docs/superpowers/plans/`
