# Clean removal

1. Remove the optional global F3 listener and protected TikTok placement broker,
   if installed, from an **Administrator PowerShell**:

   ```powershell
   .\tools\stream_workspace\Uninstall-StreamWorkspace.ps1
   ```

2. Close Streamer Console.
3. Unpin Streamer Console from the taskbar and remove the **Streamer Console**
   shortcut from `%APPDATA%\Microsoft\Windows\Start Menu\Programs`.
4. Remove the local project directory: `D:\Projects\StreamerConsole`.
5. Optionally remove runtime settings/logs from `%LOCALAPPDATA%\NeilMitchell\StreamerConsole`.
6. Optionally disable or uninstall Social Stream Ninja if it is no longer used.

The optional F3 installer creates the current user's **Lausudo Stream
Workspace.lnk** Startup shortcut. When the explicitly elevated TikTok broker is
installed, it also creates one fixed on-demand scheduled task named **Lausudo
Stream Workspace TikTok Placement** and one protected script under
`C:\Program Files\Lausudo Streamer Console`. The uninstaller removes those exact
artifacts; it creates no Run-key value or service.

Removing Streamer Console does not remove or change OBS scenes, OBS WebSocket,
Aitum, TikTok LIVE Studio, Voicemeeter, Discord, the F1/F2 AutoHotkey script,
stream credentials, or recordings. Closing the console stops only an AutoHotkey
helper instance that the console launched itself.
