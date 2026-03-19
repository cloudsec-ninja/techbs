#Requires -Version 5.1

$ScriptDir = $PSScriptRoot

if (-not (Test-Path "$ScriptDir\venv")) {
    Write-Error "Virtual environment not found. Run install.ps1 first."
    exit 1
}

& "$ScriptDir\venv\Scripts\python.exe" "$ScriptDir\app\main.py" @args
