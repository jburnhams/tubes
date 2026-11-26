@echo off
rem Launcher for Windows: runs the tubes CLI in the uv-managed project environment (same as `uv run tubes`).
uv run --project "%~dp0." tubes %*
