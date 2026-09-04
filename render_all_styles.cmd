@echo off
cd /d "%~dp0"
python -m backend.scripts.render_archviz %*
if errorlevel 1 pause
