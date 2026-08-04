"""Win32 进程查询。纯 ctypes，无第三方依赖，全部失败都降级为空值。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = -1


@dataclass(frozen=True)
class ProcRow:
    pid: int
    ppid: int
    name: str


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def snapshot() -> dict[int, ProcRow]:
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:
        return {}
    handle = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if handle == INVALID_HANDLE_VALUE:
        return {}
    try:
        return _walk_snapshot(kernel32, handle)
    finally:
        kernel32.CloseHandle(handle)


def _walk_snapshot(kernel32, handle) -> dict[int, ProcRow]:
    entry = _PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(_PROCESSENTRY32)
    table: dict[int, ProcRow] = {}
    ok = kernel32.Process32First(handle, ctypes.byref(entry))
    while ok:
        pid = int(entry.th32ProcessID)
        table[pid] = ProcRow(
            pid=pid,
            ppid=int(entry.th32ParentProcessID),
            name=entry.szExeFile.decode("mbcs", "ignore").lower(),
        )
        ok = kernel32.Process32Next(handle, ctypes.byref(entry))
    return table


CLAUDE_EXE = "claude.exe"
ERROR_ALREADY_EXISTS = 183
_instance_handle = None


def any_claude_alive(table: dict[int, ProcRow]) -> bool:
    return any(row.name == CLAUDE_EXE for row in table.values())


def claim_single_instance(name: str) -> bool:
    """用命名 Mutex 占位，已有实例在跑时返回 False。

    句柄存在模块级变量里不能丢 —— 一旦被 GC 回收，Mutex 就释放了，
    单实例保护随之失效。进程退出时由系统自动释放。
    """
    global _instance_handle
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:
        return True
    handle = kernel32.CreateMutexW(None, True, name)
    if not handle:
        return True
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _instance_handle = handle
    return True
