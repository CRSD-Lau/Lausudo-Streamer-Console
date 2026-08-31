"""Idempotent Windows workspace preparation for the Lausudo stream stack.

This module deliberately manages only application windows.  It does not connect
to OBS, send application hotkeys, or touch streaming, recording, scenes, audio,
Virtual Camera, Discord mute state, or Voicemeeter routing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Protocol, Sequence


LOGGER = logging.getLogger("streamer_console.stream_workspace")
CREATE_NO_WINDOW = 0x08000000


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True)
class Monitor:
    device: str
    bounds: Rect
    work_area: Rect
    primary: bool


@dataclass(frozen=True)
class Window:
    handle: int
    process_id: int
    executable: str
    class_name: str
    title: str


@dataclass(frozen=True)
class AppSpec:
    key: str
    executable_names: tuple[str, ...]
    title_terms: tuple[str, ...]
    command: tuple[str, ...] | None
    zone: str | None
    launch: bool = True
    minimize: bool = False
    launch_timeout: float = 12.0


class Platform(Protocol):
    def monitors(self) -> list[Monitor]: ...
    def windows(self) -> list[Window]: ...
    def foreground_window(self) -> int: ...
    def launch(self, command: Sequence[str]) -> None: ...
    def place(self, handle: int, rect: Rect) -> bool: ...
    def minimize(self, handle: int) -> bool: ...
    def restore_focus(self, handle: int) -> bool: ...


def _local_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / (
        "NeilMitchell/StreamerConsole"
    )


def _setup_logging() -> None:
    if LOGGER.handlers:
        return
    log_dir = _local_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "stream-workspace.log",
        maxBytes=512_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def _program_files() -> Path:
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files"))


def _local_app_data() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _first_file(candidates: Sequence[Path]) -> Path | None:
    return next((path for path in candidates if path.is_file()), None)


def _tiktok_executable() -> Path:
    root = _program_files() / "TikTok LIVE Studio"
    versioned = sorted(
        root.glob("*/TikTok LIVE Studio.exe"),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    return _first_file([root / "TikTok LIVE Studio Launcher.exe", *versioned]) or (
        root / "TikTok LIVE Studio Launcher.exe"
    )


def _pythonw_executable() -> Path:
    current = Path(sys.executable)
    if current.name.casefold() == "pythonw.exe" and current.is_file():
        return current
    local = _local_app_data() / "Programs/Python"
    candidates = [
        local / "Python313/pythonw.exe",
        local / "Python311/pythonw.exe",
        current.with_name("pythonw.exe"),
    ]
    return _first_file(candidates) or current


def default_apps() -> list[AppSpec]:
    """Return the approved application allowlist and layout assignments."""

    program_files = _program_files()
    local = _local_app_data()
    repo = _repo_root()
    obs = program_files / "obs-studio/bin/64bit/obs64.exe"
    tiktok = _tiktok_executable()
    discord_update = local / "Discord/Update.exe"
    chrome = program_files / "Google/Chrome/Application/chrome.exe"
    console_command = (_pythonw_executable(), repo / "run_console.pyw")
    social_url = (
        "chrome-extension://cppibjhfemifednoimlblfcmjgfhjeg/background.html"
    )

    return [
        AppSpec(
            "streamer_console",
            ("pythonw.exe", "python.exe"),
            ("Lausudo Streamer Console",),
            tuple(map(str, console_command)),
            "portrait_top",
        ),
        AppSpec(
            "discord",
            ("Discord.exe",),
            ("Discord",),
            (str(discord_update), "--processStart", "Discord.exe"),
            "portrait_bottom",
        ),
        AppSpec(
            "obs",
            ("obs64.exe",),
            ("OBS",),
            (str(obs),),
            "production_left",
        ),
        AppSpec(
            "tiktok_live_studio",
            ("TikTok LIVE Studio.exe", "TikTok LIVE Studio Launcher.exe"),
            ("TikTok LIVE Studio", "LIVE Studio"),
            (str(tiktok),),
            "production_right",
            launch_timeout=20.0,
        ),
        AppSpec(
            "social_stream_ninja",
            ("chrome.exe",),
            ("Social Stream Ninja",),
            (str(chrome), "--profile-directory=Default", f"--app={social_url}"),
            None,
            minimize=True,
        ),
        AppSpec(
            "spotify",
            ("Spotify.exe",),
            (),
            (
                "explorer.exe",
                "shell:AppsFolder\\SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify",
            ),
            None,
            minimize=True,
        ),
        AppSpec(
            "voicemeeter",
            ("voicemeeter.exe", "voicemeeter_x64.exe", "voicemeeterpro.exe", "voicemeeterpro_x64.exe"),
            ("Voicemeeter",),
            None,
            "production_right",
            launch=False,
            minimize=True,
        ),
    ]


def identify_roles(monitors: Sequence[Monitor]) -> dict[str, Monitor]:
    """Identify the approved three-display topology or return an empty mapping."""

    gaming = next(
        (
            monitor
            for monitor in monitors
            if monitor.primary
            and monitor.bounds.width == 2560
            and monitor.bounds.height == 1440
        ),
        None,
    )
    if gaming is None:
        return {}
    production = next(
        (
            monitor
            for monitor in monitors
            if not monitor.primary
            and monitor.bounds.width == 2560
            and monitor.bounds.height == 1440
            and monitor.bounds.top < gaming.bounds.top
        ),
        None,
    )
    portrait = next(
        (
            monitor
            for monitor in monitors
            if not monitor.primary
            and monitor.bounds.width == 1080
            and monitor.bounds.height == 1920
            and monitor.bounds.left < gaming.bounds.left
        ),
        None,
    )
    if production is None or portrait is None:
        return {}
    return {"gaming": gaming, "production": production, "portrait": portrait}


def build_zones(roles: dict[str, Monitor]) -> dict[str, Rect]:
    production = roles["production"].work_area
    portrait = roles["portrait"].work_area
    production_split = production.left + round(production.width * 0.60)
    portrait_split = portrait.top + round(portrait.height * 0.38)
    return {
        "production_left": Rect(
            production.left, production.top, production_split, production.bottom
        ),
        "production_right": Rect(
            production_split, production.top, production.right, production.bottom
        ),
        "portrait_top": Rect(
            portrait.left, portrait.top, portrait.right, portrait_split
        ),
        "portrait_bottom": Rect(
            portrait.left, portrait_split, portrait.right, portrait.bottom
        ),
    }


def _matches(window: Window, app: AppSpec) -> bool:
    executable = Path(window.executable).name.casefold()
    if executable not in {name.casefold() for name in app.executable_names}:
        return False
    if not app.title_terms:
        return True
    title = window.title.casefold()
    return any(term.casefold() in title for term in app.title_terms)


def _find_window(platform: Platform, app: AppSpec) -> Window | None:
    return next((window for window in platform.windows() if _matches(window, app)), None)


def _wait_for_window(platform: Platform, app: AppSpec) -> Window | None:
    deadline = time.monotonic() + app.launch_timeout
    while time.monotonic() < deadline:
        window = _find_window(platform, app)
        if window is not None:
            return window
        time.sleep(0.20)
    return None


def apply_workspace(
    platform: Platform,
    apps: Sequence[AppSpec] | None = None,
    *,
    dry_run: bool = False,
) -> tuple[bool, list[dict[str, str]]]:
    """Prepare the approved workspace, returning success and sanitized actions."""

    roles = identify_roles(platform.monitors())
    if not roles:
        LOGGER.error("Expected three-display topology was not found; no changes made")
        return False, [{"app": "workspace", "action": "aborted_missing_monitors"}]

    zones = build_zones(roles)
    foreground = platform.foreground_window()
    actions: list[dict[str, str]] = []
    success = True

    for app in apps or default_apps():
        window = _find_window(platform, app)
        if window is None and not app.launch:
            actions.append({"app": app.key, "action": "not_running_skipped"})
            continue
        if window is None:
            if app.command is None or not Path(app.command[0]).is_file() and app.command[0].casefold() != "explorer.exe":
                LOGGER.error("Approved executable missing app=%s", app.key)
                actions.append({"app": app.key, "action": "executable_missing"})
                success = False
                continue
            actions.append({"app": app.key, "action": "launch"})
            if dry_run:
                if app.zone is not None:
                    actions.append({"app": app.key, "action": f"place_{app.zone}"})
                if app.minimize:
                    actions.append({"app": app.key, "action": "minimize"})
                continue
            try:
                platform.launch(app.command)
                window = _wait_for_window(platform, app)
            except OSError as exc:
                LOGGER.error("Launch failed app=%s type=%s", app.key, type(exc).__name__)
                window = None
            if window is None:
                LOGGER.error("Window readiness timed out app=%s", app.key)
                actions.append({"app": app.key, "action": "window_timeout"})
                success = False
                continue
        else:
            actions.append({"app": app.key, "action": "reuse"})

        if app.zone is not None:
            actions.append({"app": app.key, "action": f"place_{app.zone}"})
            if not dry_run and not platform.place(window.handle, zones[app.zone]):
                LOGGER.error("Window placement failed app=%s", app.key)
                success = False
        if app.minimize:
            actions.append({"app": app.key, "action": "minimize"})
            if not dry_run and not platform.minimize(window.handle):
                LOGGER.error("Window minimize failed app=%s", app.key)
                success = False

    if foreground:
        actions.append({"app": "foreground", "action": "restore"})
        if not dry_run and not platform.restore_focus(foreground):
            LOGGER.warning("Original foreground window could not be restored")

    LOGGER.info("Workspace apply finished success=%s dry_run=%s", success, dry_run)
    return success, actions


class WindowsPlatform:
    """Minimal Win32 adapter; no application-specific control surfaces."""

    MONITORINFOF_PRIMARY = 1
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SW_MINIMIZE = 6
    SW_RESTORE = 9
    SWP_NOACTIVATE = 0x0010
    SWP_NOZORDER = 0x0004

    class _MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Stream workspace control is Windows-only")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.OpenProcess.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        )
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.user32.GetMonitorInfoW.argtypes = (
            wintypes.HMONITOR,
            ctypes.POINTER(self._MONITORINFOEXW),
        )
        self.user32.GetMonitorInfoW.restype = wintypes.BOOL
        self.user32.IsWindowVisible.argtypes = (wintypes.HWND,)
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        self.user32.GetWindowTextLengthW.restype = ctypes.c_int
        self.user32.GetWindowTextW.argtypes = (
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        )
        self.user32.GetWindowTextW.restype = ctypes.c_int
        self.user32.GetClassNameW.argtypes = (
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        )
        self.user32.GetClassNameW.restype = ctypes.c_int
        self.user32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        )
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.GetForegroundWindow.argtypes = ()
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.IsWindow.argtypes = (wintypes.HWND,)
        self.user32.IsWindow.restype = wintypes.BOOL
        self.user32.ShowWindowAsync.argtypes = (wintypes.HWND, ctypes.c_int)
        self.user32.ShowWindowAsync.restype = wintypes.BOOL
        self.user32.SetWindowPos.argtypes = (
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        )
        self.user32.SetWindowPos.restype = wintypes.BOOL
        self.user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
        self.user32.SetForegroundWindow.restype = wintypes.BOOL

    @staticmethod
    def _rect(value: wintypes.RECT) -> Rect:
        return Rect(value.left, value.top, value.right, value.bottom)

    def monitors(self) -> list[Monitor]:
        results: list[Monitor] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(wintypes.RECT),
            wintypes.LPARAM,
        )

        def collect(handle, _dc, _rect, _data):
            info = self._MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(info)
            if self.user32.GetMonitorInfoW(handle, ctypes.byref(info)):
                results.append(
                    Monitor(
                        info.szDevice,
                        self._rect(info.rcMonitor),
                        self._rect(info.rcWork),
                        bool(info.dwFlags & self.MONITORINFOF_PRIMARY),
                    )
                )
            return True

        self.user32.EnumDisplayMonitors(None, None, callback_type(collect), 0)
        return results

    def _process_path(self, process_id: int) -> str:
        handle = self.kernel32.OpenProcess(
            self.PROCESS_QUERY_LIMITED_INFORMATION, False, process_id
        )
        if not handle:
            return ""
        try:
            capacity = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(capacity.value)
            if self.kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(capacity)
            ):
                return buffer.value
            return ""
        finally:
            self.kernel32.CloseHandle(handle)

    def windows(self) -> list[Window]:
        results: list[Window] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def collect(handle, _data):
            if not self.user32.IsWindowVisible(handle):
                return True
            length = self.user32.GetWindowTextLengthW(handle)
            if length <= 0:
                return True
            title = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(handle, title, length + 1)
            class_name = ctypes.create_unicode_buffer(256)
            self.user32.GetClassNameW(handle, class_name, 256)
            process_id = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
            executable = self._process_path(process_id.value)
            if executable:
                results.append(
                    Window(
                        int(handle),
                        process_id.value,
                        executable,
                        class_name.value,
                        title.value,
                    )
                )
            return True

        self.user32.EnumWindows(callback_type(collect), 0)
        return results

    def foreground_window(self) -> int:
        return int(self.user32.GetForegroundWindow() or 0)

    def launch(self, command: Sequence[str]) -> None:
        subprocess.Popen(
            list(command),
            close_fds=True,
            creationflags=CREATE_NO_WINDOW,
        )

    def place(self, handle: int, rect: Rect) -> bool:
        self.user32.ShowWindowAsync(handle, self.SW_RESTORE)
        return bool(
            self.user32.SetWindowPos(
                handle,
                None,
                rect.left,
                rect.top,
                rect.width,
                rect.height,
                self.SWP_NOACTIVATE | self.SWP_NOZORDER,
            )
        )

    def minimize(self, handle: int) -> bool:
        return bool(self.user32.ShowWindowAsync(handle, self.SW_MINIMIZE))

    def restore_focus(self, handle: int) -> bool:
        if not self.user32.IsWindow(handle):
            return False
        return bool(self.user32.SetForegroundWindow(handle))


class _Mutex:
    def __init__(self) -> None:
        self.handle = None

    def __enter__(self) -> bool:
        if os.name != "nt":
            return True
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        self.handle = kernel32.CreateMutexW(None, False, "Local\\NeilMitchell.StreamWorkspace")
        return bool(self.handle) and ctypes.get_last_error() != 183

    def __exit__(self, *_args) -> None:
        if self.handle:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.CloseHandle.restype = wintypes.BOOL
            kernel32.CloseHandle(self.handle)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the Lausudo stream workspace")
    parser.add_argument("command", choices=("apply", "plan", "validate"), nargs="?", default="apply")
    parser.add_argument("--json", action="store_true", help="print sanitized actions")
    args = parser.parse_args(argv)
    _setup_logging()

    try:
        platform = WindowsPlatform()
    except OSError as exc:
        LOGGER.error("Platform initialization failed type=%s", type(exc).__name__)
        return 3

    with _Mutex() as acquired:
        if not acquired:
            LOGGER.info("Workspace apply already in progress; duplicate request ignored")
            return 0
        dry_run = args.command in {"plan", "validate"}
        success, actions = apply_workspace(platform, dry_run=dry_run)
        if args.json:
            print(json.dumps(actions, indent=2))
        return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
