# TaskLight 🚦

Windows 桌面红绿灯，余光一扫就知道 Claude Code 在忙什么。

不用切窗口、不用盯屏幕 —— 它把「Claude 卡住在等你批准」和「其实早跑完了」这两件最耗时间的事，变成桌面角落一盏灯。**聚合所有会话**：几个 CLI 窗口加 VS Code 扩展，汇总成一盏。

| 灯 | 含义 | 默认表现 |
|---|---|---|
| 🔴🟠 红+橙 | Claude 停下来等你**批准权限** —— 不回去它就一直卡着 | **快闪** |
| 🔴 红 | Claude 正在干活，可以走开 | 慢闪 |
| 🟠 橙 | 前台都停了，但后台子 Agent / Task / Bash 还在跑 | 慢闪 |
| 🟢 绿 | 全部完成，待机 | 常亮 |

多窗口时按优先级聚合，取最紧急的那个。闪烁节奏和规则可在**托盘右键 → 设置**里改。

## 快速上手

```powershell
python -m pip install -e .
python install_hooks.py
```

然后**重启 Claude Code**（hook 在会话启动时加载，这步不能省），双击 `start.cmd`。

| 操作 | 效果 |
|---|---|
| 灯上左键拖动 | 移动 |
| 拖边缘或四角 | 等比缩放 |
| 托盘左键 | 显示 / 隐藏 |
| 托盘右键 → 设置 | 调闪烁节奏与规则 |
| 托盘右键 → 退出 | 唯一的退出入口 |

位置尺寸会记住。悬浮窗刻意不响应右键，免得误点关掉。

**卸载**：`python install_hooks.py --uninstall`，再删 `~\.claude\tasklight\`。

> 📖 详细说明、设置项、故障排查见 **[使用文档](docs/USAGE.md)**

## 工作原理

```
Claude Code hooks ──写──► ~\.claude\tasklight\sessions\<session_id>.json
                                      │
                                      ▼  每 400ms 读取并聚合
                              悬浮窗 + 托盘图标
```

三个关键设计：

**全部用低频 hook。** 挂的 10 个事件都是每轮对话触发一次的，刻意不用 `PreToolUse`/`PostToolUse` —— Windows 上每次 hook 都要冷启动一个 Python 进程（约 100ms），挂在高频事件上会实打实拖慢 Claude Code。

**后台任务不靠推断。** `Stop` 的 payload 直接带 `background_tasks` 列表，是 Claude Code 给出的事实，不用扫进程树去猜。

**子 Agent 计数用「一个 ID 一个空文件」。** 并行派多个 Agent 时 `SubagentStart` 会并发触发，读-改-写同一个 JSON 必然丢更新；一个 Agent 一个空文件则天然无竞争、不用加锁。

## 项目结构

```
tasklight/
├── state.py       灯色判定（纯函数，零 I/O）
├── store.py       槽位读写、陈旧清理、窗口位置
├── config.py      闪烁配置
├── assets.py      灯态图加载与红+橙合成
├── layered.py     Win32 分层窗口逐像素 alpha 绘制
├── widget.py      悬浮窗：拖动、缩放、闪烁引擎
├── settings_window.py  设置界面
├── tray.py        托盘图标
└── winproc.py     进程快照、单实例互斥
hooks/tasklight_hook.py   10 个事件的分派入口
install_hooks.py          幂等安装 / 卸载
```

## 开发

```powershell
python -m pytest -q                 # 103 项测试
python scripts/preview_widget.py    # 手动预览四种灯态
```

设计文档见 `docs/superpowers/specs/`，hook payload 实测结论见 `docs/hook-payload-findings.md`。

## 环境要求

Windows 10/11 · Python 3.13+（需 tkinter）· 依赖 `pystray` + `Pillow`（仅界面侧，hook 只用标准库）
