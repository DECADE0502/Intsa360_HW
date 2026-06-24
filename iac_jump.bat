@echo off
cd /d "%~dp0"
wscript.exe "%~dp0launch_tool_suite_hidden.vbs" "%~dp0launch_tool_suite.ps1" %*
exit /b
