"""Win32 进程查询。纯 ctypes，无第三方依赖，全部失败都降级为空值。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INVALID_HANDLE_VALUE = -1
FILETIME_EPOCH_DELTA = 11644473600.0
FILETIME_TICKS_PER_SECOND = 1e7


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


def created_at(pid: int) -> float | None:
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:
        return None
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        unused = (wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME())
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(unused[0]),
            ctypes.byref(unused[1]),
            ctypes.byref(unused[2]),
        )
        if not ok:
            return None
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return ticks / FILETIME_TICKS_PER_SECOND - FILETIME_EPOCH_DELTA
    finally:
        kernel32.CloseHandle(handle)


def find_ancestor_pid(
    table: dict[int, ProcRow], start_pid: int, target_name: str, max_depth: int = 6
) -> int | None:
    pid = start_pid
    seen = set()
    for _ in range(max_depth):
        row = table.get(pid)
        if row is None or pid in seen:
            return None
        if row.name == target_name:
            return pid
        seen.add(pid)
        pid = row.ppid
    return None
