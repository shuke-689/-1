# -*- coding: utf-8 -*-
"""列出所有 python 进程的 PID / 父 PID / 命令行（用 NtQueryInformationProcess）。

为什么不用 PowerShell/WMIC：本机 PowerShell 通道当前不可用、wmic 已被移除。
这里直接用 ntdll 的 ProcessCommandLineInformation(60) 取命令行，只读、无副作用。
"""
import ctypes
import ctypes.wintypes as wt
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ProcessCommandLineInformation = 60
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def cmdline_of(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        return None
    try:
        size = wt.ULONG(0)
        ntdll.NtQueryInformationProcess(ctypes.c_void_p(h), ProcessCommandLineInformation,
                                        None, 0, ctypes.byref(size))
        if size.value == 0:
            return ""
        buf = ctypes.create_string_buffer(size.value)
        st = ntdll.NtQueryInformationProcess(ctypes.c_void_p(h), ProcessCommandLineInformation,
                                             buf, size.value, ctypes.byref(size))
        if st != 0:
            return None
        # UNICODE_STRING { USHORT Len; USHORT MaxLen; PWSTR Buffer; } 后跟字符串数据
        length = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort))[0]
        return buf.raw[16:16 + length].decode("utf-16-le", "replace")
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(h))


def main():
    # CreateToolhelp32Snapshot 枚举进程
    TH32CS_SNAPPROCESS = 0x2

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                    ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                    ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_char * 260)]

    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    e = PROCESSENTRY32()
    e.dwSize = ctypes.sizeof(PROCESSENTRY32)
    rows = []
    ok = kernel32.Process32First(snap, ctypes.byref(e))
    while ok:
        name = e.szExeFile.decode("mbcs", "replace")
        if "python" in name.lower():
            rows.append((e.th32ProcessID, e.th32ParentProcessID, cmdline_of(e.th32ProcessID)))
        ok = kernel32.Process32Next(snap, ctypes.byref(e))
    kernel32.CloseHandle(snap)

    print("python 进程数：%d" % len(rows))
    for pid, ppid, cl in rows:
        print("-" * 70)
        print("PID=%d  PPID=%d" % (pid, ppid))
        print("  CMD=%s" % (cl if cl else "(取不到)"))


if __name__ == "__main__":
    main()
