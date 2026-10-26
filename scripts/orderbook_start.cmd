@echo off
REM Launch wrapper for the order book collector.
REM
REM Exists so the Scheduled Task command has no nested quotes. Passing a powershell.exe
REM invocation with a quoted -File path directly to schtasks /TR means three levels of quoting,
REM which cmd and PowerShell escape differently -- that is how the first registration attempt
REM silently produced no task at all. A .cmd file takes no arguments, so /TR is one plain path.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0orderbook_service.ps1"
