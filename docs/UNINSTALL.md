# Clean removal

1. Close Streamer Console.
2. Unpin Streamer Console from the taskbar and remove the **Streamer Console**
   shortcut from `%APPDATA%\Microsoft\Windows\Start Menu\Programs`.
3. Remove the local project directory: `D:\Projects\StreamerConsole`.
4. Optionally remove runtime settings/logs from `%LOCALAPPDATA%\NeilMitchell\StreamerConsole`.
5. Optionally disable or uninstall Social Stream Ninja if it is no longer used.

This installation does not create a Windows Startup entry, Run-key value, or
scheduled task. If you add one manually later, remove that registration as part
of uninstalling.

Removing Streamer Console does not remove or change OBS scenes, OBS WebSocket,
Aitum, TikTok LIVE Studio, Voicemeeter, Discord, the F1/F2 AutoHotkey script,
stream credentials, or recordings. Closing the console stops only an AutoHotkey
helper instance that the console launched itself.
