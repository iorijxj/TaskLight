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

**全部 hook 都是每轮触发一次的低频事件**（`UserPromptSubmit` / `Stop` / `Notification` / `SubagentStart|Stop` 等），一个高频或中频 hook 都没有 —— Windows 上每个 hook 都要冷启动一个 Python 进程，挂在 `PreToolUse` 或 `PostToolUse` 上会实打实拖慢 Claude Code。

后台任务的状态直接取自 `Stop` payload 里的 `background_tasks` 字段（Claude Code 给出的事实），不做任何推断。

子 Agent 与 Task 的计数用「一个 ID 一个空文件」表示，而不是读-改-写一个共享 JSON —— 并行派多个 Agent 时 `SubagentStart` 会并发触发，读-改-写必然丢更新。

## 已知限制

- 灯每 400ms 刷新一次；崩溃兜底（`claude.exe` 全没了就清空槽位）按 2 秒节流
- 仅支持 Windows（依赖 Win32 进程 API）
- 不监控 SSH / WSL 上的远程会话
- **hook 侧永远不能引入第三方库** —— 命令行带 `-S` 跳过了 site-packages 扫描
- 若 `SubagentStop` 漏触发，橙灯会多亮一会儿，靠 `SessionEnd` 或 4 小时超时兜底

## 性能

hook 冷启动实测（Python 3.13.2）：约 **100ms**，其中 49ms 是 Python 解释器自身启动，无法再压。每轮对话触发两次（`UserPromptSubmit` + `Stop`）。

优化手段：命令行 `-S` 跳过 site 扫描（省 17ms）、延迟 import `shutil`（它连带 bz2/lzma，省 20ms）。

GUI 侧每 400ms 一次轮询（读槽位约 1ms），每 2 秒一次进程快照（446 个进程约 11ms）。

## 开发

```bash
python -m pytest -v                 # 全部测试
python scripts/preview_widget.py    # 手动预览四种灯态
```

设计文档见 `docs/superpowers/specs/`，实现计划见 `docs/superpowers/plans/`。
