# TaskLight 🚦

Windows 桌面红绿灯，余光一扫就知道 Claude Code 在忙什么。聚合所有会话（CLI + VS Code 扩展），全局一盏灯。

## 灯态

| 灯 | 含义 |
|---|---|
| 🔴 闪烁 | Claude 停下来等你批准权限 —— 不回去它就一直卡着 |
| 🔴 常亮 | Claude 正在干活，可以走开 |
| 🟠 常亮 | 前台都停了，但后台子 Agent / Task / Bash 还在跑 |
| 🟢 常亮 | 全部完成，待机 |

多个窗口时按优先级聚合：任一会话等你批准就闪红，任一会话在干活就红，全停下但还有后台活就橙，彻底空了才绿。

## 安装

```bash
python -m pip install -e .
python install_hooks.py
```

`install_hooks.py` 会把 hooks 幂等合并进 `~\.claude\settings.json`（自动备份 `.bak`，不动你已有的条目）。**重启 Claude Code** 后生效。

然后双击 `start.cmd` 启动红绿灯。左键拖拽移动，右键或托盘菜单退出。

## 卸载

```bash
python install_hooks.py --uninstall
```

再删掉 `~\.claude\tasklight\` 目录即可。

## 工作原理

```
Claude Code hooks ──► ~\.claude\tasklight\sessions\<session_id>.json
                             │
                             ▼  每 400ms 轮询聚合
                      悬浮窗 + 托盘图标
```

hook 只挂每轮触发一次的低频事件（`UserPromptSubmit` / `Stop` / `Notification` / `SubagentStart|Stop` 等），刻意不用 `PreToolUse` —— Windows 上每个 hook 都要冷启动一个 Python 进程，挂在高频事件上会实打实拖慢 Claude Code。

子 Agent 与 Task 的计数用「一个 ID 一个空文件」表示，而不是读-改-写一个共享 JSON —— 并行派多个 Agent 时 `SubagentStart` 会并发触发，读-改-写必然丢更新。

## 已知限制

- **后台 Bash 是推断而非精确判定**。Claude Code 的后台 Bash 完成时不发任何 hook 事件（[issue #45781](https://github.com/anthropics/claude-code/issues/45781) 已 closed as not planned），只能靠「进程创建时间晚于该会话起后台命令的时刻」来识别。常驻 MCP 进程因创建时间更早而被排除
- 同一会话先起长任务、再起短任务时，短任务结束后长任务仍在跑 —— 此时会误判为已完成而转绿（`bg_since` 只记最近一次）
- 进程扫描按 2 秒节流，后台任务结束到转绿最长有 2.4 秒延迟
- 仅支持 Windows（依赖 Win32 进程 API 与 tkinter 的 `-transparentcolor`）
- 不监控 SSH / WSL 上的远程会话
- **hook 侧永远不能引入第三方库** —— 命令行带 `-S` 跳过了 site-packages 扫描

## 性能

hook 冷启动实测（Python 3.13.2）：

| 场景 | 耗时 |
|---|---|
| `Stop` / `UserPromptSubmit` | ~101ms |
| 前台 Bash（提前退出） | ~96ms |
| 后台 Bash（含扫进程） | ~131ms |

其中约 49ms 是 Python 解释器自身启动，无法再压。GUI 侧每 400ms 一次轮询，每 2 秒一次进程扫描（446 个进程约 11ms）。

## 开发

```bash
python -m pytest -v                 # 全部测试
python scripts/preview_widget.py    # 手动预览四种灯态
```

设计文档见 `docs/superpowers/specs/`，实现计划见 `docs/superpowers/plans/`。
