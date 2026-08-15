[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonWindowed = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\pythonw.exe'
$Launcher = Join-Path $ProjectDirectory 'run_console.pyw'

if (-not (Test-Path -LiteralPath $PythonWindowed -PathType Leaf)) {
    throw "Python 3.13 pythonw.exe was not found at $PythonWindowed"
}

if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) {
    throw "Streamer Console launcher was not found at $Launcher"
}

Start-Process `
    -FilePath $PythonWindowed `
    -ArgumentList @($Launcher) `
    -WorkingDirectory $ProjectDirectory `
    -WindowStyle Hidden
