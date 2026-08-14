"""Safe bridge to the existing global streaming hotkeys.

The Streamer Console deliberately owns no OBS or Discord toggle logic.  It
only verifies that the relevant applications are present and asks Windows to
emit the same F1/F2 keys used by the existing AutoHotkey helper.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import ctypes
from ctypes import wintypes
import ntpath
import sys
from typing import Callable, Iterable, Mapping


ProcessProvider = Callable[[], Iterable[str]]
KeySender = Callable[[int], None]


@dataclass(frozen=True, slots=True)
class ControlResult:
    """Structured outcome returned by every control action."""

    control: str
    key: str
    success: bool
    code: str
    message: str
    dependencies: Mapping[str, bool]
    missing: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for UI/API layers."""

        return asdict(self)


class ControlBridge:
    """Invoke the canonical F1/F2 automation without duplicating its logic.

    ``process_provider`` and ``key_sender`` are injectable so callers can test
    every branch without enumerating real processes or emitting real keys.
    """

    VK_F1 = 0x70
    VK_F2 = 0x71

    _AUTOHOTKEY_NAMES = frozenset(
        {
            "autohotkey.exe",
            "autohotkey32.exe",
            "autohotkey64.exe",
            "autohotkeyu32.exe",
            "autohotkeyu64.exe",
        }
    )
    _OBS_NAMES = frozenset({"obs.exe", "obs32.exe", "obs64.exe"})
    _DISCORD_NAMES = frozenset(
        {"discord.exe", "discordcanary.exe", "discordptb.exe"}
    )

    def __init__(
        self,
        *,
        process_provider: ProcessProvider | None = None,
        key_sender: KeySender | None = None,
        platform_name: str | None = None,
    ) -> None:
        self._process_provider = process_provider or _list_windows_process_names
        self._key_sender = key_sender or _send_windows_key
        self._platform_name = platform_name if platform_name is not None else sys.platform

    def toggle_brb_privacy(self) -> ControlResult:
        """Send F1 after confirming AutoHotkey and OBS are running."""

        return self._invoke(
            control="brb_privacy",
            key="F1",
            virtual_key=self.VK_F1,
            requirements={
                "autohotkey": self._AUTOHOTKEY_NAMES,
                "obs": self._OBS_NAMES,
            },
        )

    def toggle_discord_mute(self) -> ControlResult:
        """Send F2 after confirming AutoHotkey and Discord are running."""

        return self._invoke(
            control="discord_mute",
            key="F2",
            virtual_key=self.VK_F2,
            requirements={
                "autohotkey": self._AUTOHOTKEY_NAMES,
                "discord": self._DISCORD_NAMES,
            },
        )

    # Short aliases are convenient for signal/slot and HTTP route adapters.
    trigger_brb = toggle_brb_privacy
    trigger_discord_mute = toggle_discord_mute

    def _invoke(
        self,
        *,
        control: str,
        key: str,
        virtual_key: int,
        requirements: Mapping[str, frozenset[str]],
    ) -> ControlResult:
        empty_status = {name: False for name in requirements}
        if not _is_windows(self._platform_name):
            return ControlResult(
                control=control,
                key=key,
                success=False,
                code="unsupported_platform",
                message="Streamer controls are available only on Windows.",
                dependencies=empty_status,
                missing=tuple(requirements),
            )

        try:
            running = {
                ntpath.basename(str(name)).casefold()
                for name in self._process_provider()
                if str(name).strip()
            }
        except Exception as exc:  # Convert an OS inspection failure for the UI.
            return ControlResult(
                control=control,
                key=key,
                success=False,
                code="process_check_failed",
                message=f"Could not verify required applications: {exc}",
                dependencies=empty_status,
                missing=tuple(requirements),
            )

        status = {
            label: bool(running.intersection(process_names))
            for label, process_names in requirements.items()
        }
        missing = tuple(label for label, present in status.items() if not present)
        if missing:
            return ControlResult(
                control=control,
                key=key,
                success=False,
                code="dependency_missing",
                message=f"Cannot send {key}; not running: {', '.join(missing)}.",
                dependencies=status,
                missing=missing,
            )

        try:
            self._key_sender(virtual_key)
        except Exception as exc:  # Surface SendInput failure without crashing the app.
            return ControlResult(
                control=control,
                key=key,
                success=False,
                code="send_input_failed",
                message=f"Windows could not send {key}: {exc}",
                dependencies=status,
            )

        return ControlResult(
            control=control,
            key=key,
            success=True,
            code="sent",
            message=f"{key} sent to the existing global automation.",
            dependencies=status,
        )


def _is_windows(platform_name: str) -> bool:
    value = platform_name.casefold()
    return value == "windows" or value.startswith("win")


def _list_windows_process_names() -> tuple[str, ...]:
    """Enumerate executable names with Toolhelp32 (read-only, no shell)."""

    if not _is_windows(sys.platform):
        raise OSError("Windows process enumeration is unavailable on this platform")

    th32cs_snapprocess = 0x00000002
    max_path = 260
    ulong_ptr = wintypes.WPARAM

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ulong_ptr),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * max_path),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    )
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    )
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    invalid_handle_value = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle_value:
        raise ctypes.WinError(ctypes.get_last_error())

    names: list[str] = []
    entry = ProcessEntry32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                names.append(entry.szExeFile)
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
        else:
            error = ctypes.get_last_error()
            # ERROR_NO_MORE_FILES also represents a valid empty snapshot.
            if error not in (0, 18):
                raise ctypes.WinError(error)
    finally:
        kernel32.CloseHandle(snapshot)

    return tuple(names)


def _send_windows_key(virtual_key: int) -> None:
    """Emit one function-key press through Win32 SendInput."""

    if not _is_windows(sys.platform):
        raise OSError("Windows keyboard input is unavailable on this platform")

    input_keyboard = 1
    keyeventf_keyup = 0x0002
    ulong_ptr = wintypes.WPARAM

    class MouseInput(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ulong_ptr),
        ]

    class KeyboardInput(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ulong_ptr),
        ]

    class HardwareInput(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class InputUnion(ctypes.Union):
        _fields_ = [
            ("mi", MouseInput),
            ("ki", KeyboardInput),
            ("hi", HardwareInput),
        ]

    class Input(ctypes.Structure):
        _anonymous_ = ("payload",)
        _fields_ = [("type", wintypes.DWORD), ("payload", InputUnion)]

    inputs = (Input * 2)(
        Input(
            type=input_keyboard,
            ki=KeyboardInput(
                wVk=virtual_key,
                wScan=0,
                dwFlags=0,
                time=0,
                dwExtraInfo=0,
            ),
        ),
        Input(
            type=input_keyboard,
            ki=KeyboardInput(
                wVk=virtual_key,
                wScan=0,
                dwFlags=keyeventf_keyup,
                time=0,
                dwExtraInfo=0,
            ),
        ),
    )

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = (
        wintypes.UINT,
        ctypes.POINTER(Input),
        ctypes.c_int,
    )
    user32.SendInput.restype = wintypes.UINT
    sent = user32.SendInput(len(inputs), inputs, ctypes.sizeof(Input))
    if sent != len(inputs):
        error = ctypes.get_last_error()
        if error:
            raise ctypes.WinError(error)
        raise OSError(f"SendInput accepted {sent} of {len(inputs)} keyboard events")


__all__ = ["ControlBridge", "ControlResult"]
