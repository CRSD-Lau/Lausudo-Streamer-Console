"""Lifecycle manager for the existing F1/F2 AutoHotkey helper.

The Streamer Console owns only helpers that it starts itself.  An exact
``PrivacyToggle.ahk`` instance that predates the console is detected and left
running when the console exits.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Protocol


LOGGER = logging.getLogger("streamer_console.hotkey_helper")

DEFAULT_SCRIPT_PATH = Path(
    r"D:\Projects\OBS-Tools\PrivacyToggle\PrivacyToggle.ahk"
)
DEFAULT_EXECUTABLE_CANDIDATES = (
    Path(r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe"),
    Path(r"C:\Program Files\AutoHotkey\AutoHotkey.exe"),
)


class ManagedProcess(Protocol):
    """Subset of :class:`subprocess.Popen` used by the manager."""

    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


ScriptChecker = Callable[[Path], bool]
ProcessLauncher = Callable[[Path, Path], ManagedProcess]
PathChecker = Callable[[Path], bool]


class HotkeyHelperManager:
    """Start and stop the canonical AutoHotkey helper with the application."""

    def __init__(
        self,
        *,
        executable_path: Path | None = None,
        script_path: Path | None = None,
        platform_name: str | None = None,
        environ: Mapping[str, str] | None = None,
        script_checker: ScriptChecker | None = None,
        process_launcher: ProcessLauncher | None = None,
        path_checker: PathChecker | None = None,
    ) -> None:
        environment = os.environ if environ is None else environ
        self._platform_name = platform_name if platform_name is not None else sys.platform
        self.script_path = script_path or Path(
            environment.get("STREAMER_CONSOLE_AHK_SCRIPT", str(DEFAULT_SCRIPT_PATH))
        )
        self.executable_path = executable_path or _resolve_executable(environment)
        self._script_checker = script_checker or _is_script_running
        self._process_launcher = process_launcher or _launch_process
        self._path_checker = path_checker or Path.is_file
        self._managed_process: ManagedProcess | None = None
        self._external_instance = False

    @property
    def owns_process(self) -> bool:
        """Whether this manager launched the currently tracked helper."""

        return self._managed_process is not None

    def start(self) -> bool:
        """Ensure the helper is available, launching it when necessary."""

        if not _is_windows(self._platform_name):
            return False
        if self._managed_process is not None and self._managed_process.poll() is None:
            return True

        self._managed_process = None
        self._external_instance = False
        try:
            if self._script_checker(self.script_path):
                self._external_instance = True
                LOGGER.info("AutoHotkey helper already running; ownership remains external")
                return True
        except Exception as exc:
            LOGGER.warning(
                "AutoHotkey helper inspection failed type=%s; attempting managed launch",
                type(exc).__name__,
            )

        if self.executable_path is None or not self._path_checker(self.executable_path):
            LOGGER.error("AutoHotkey v2 executable was not found")
            return False
        if not self._path_checker(self.script_path):
            LOGGER.error("PrivacyToggle AutoHotkey script was not found")
            return False

        try:
            self._managed_process = self._process_launcher(
                self.executable_path, self.script_path
            )
        except Exception as exc:
            LOGGER.error("AutoHotkey helper launch failed type=%s", type(exc).__name__)
            return False

        LOGGER.info("AutoHotkey helper started with Streamer Console")
        return True

    def stop(self) -> None:
        """Stop only the helper process launched by this manager."""

        process = self._managed_process
        self._managed_process = None
        if process is None:
            if self._external_instance:
                LOGGER.info("Externally owned AutoHotkey helper left running")
            self._external_instance = False
            return

        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
        except Exception as exc:
            LOGGER.warning("AutoHotkey helper shutdown failed type=%s", type(exc).__name__)
        else:
            LOGGER.info("AutoHotkey helper stopped with Streamer Console")


def _resolve_executable(environment: Mapping[str, str]) -> Path | None:
    override = environment.get("STREAMER_CONSOLE_AHK_EXE", "").strip()
    if override:
        return Path(override)
    discovered = shutil.which("AutoHotkey64.exe") or shutil.which("AutoHotkey.exe")
    if discovered:
        return Path(discovered)
    return next((path for path in DEFAULT_EXECUTABLE_CANDIDATES if path.is_file()), None)


def _is_windows(platform_name: str) -> bool:
    value = platform_name.casefold()
    return value == "windows" or value.startswith("win")


def _is_script_running(script_path: Path) -> bool:
    """Check exact AutoHotkey command lines without returning their contents."""

    powershell = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
    if not powershell:
        raise OSError("PowerShell is unavailable for helper inspection")
    environment = os.environ.copy()
    environment["STREAMER_CONSOLE_AHK_SCRIPT"] = str(script_path.resolve())
    command = (
        "$target=[IO.Path]::GetFullPath($env:STREAMER_CONSOLE_AHK_SCRIPT);"
        "$match=Get-CimInstance Win32_Process -ErrorAction Stop |"
        "Where-Object {$_.Name -like 'AutoHotkey*.exe' -and $_.CommandLine -and "
        "$_.CommandLine.IndexOf($target,[StringComparison]::OrdinalIgnoreCase) -ge 0} |"
        "Select-Object -First 1;"
        "if($null -ne $match){exit 0}else{exit 1}"
    )
    completed = subprocess.run(
        [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        creationflags=0x08000000,
        timeout=5.0,
    )
    return completed.returncode == 0


def _launch_process(executable_path: Path, script_path: Path) -> ManagedProcess:
    return subprocess.Popen(
        [str(executable_path), str(script_path)],
        cwd=str(script_path.parent),
        close_fds=True,
        creationflags=0x08000000,
    )


__all__ = ["HotkeyHelperManager"]
