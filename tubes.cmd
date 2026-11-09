@echo off
rem Launcher for Windows: runs the app CLI with the project environment. Override the interpreter with TUBES_PYTHON.
set "ROOT=%~dp0"
if "%TUBES_PYTHON%"=="" set "TUBES_PYTHON=%ROOT%.venv\Scripts\python.exe"
set "PYTHONPATH=%ROOT%src"
set "PYTHONWARNINGS=ignore"
"%TUBES_PYTHON%" -m tubes %*
