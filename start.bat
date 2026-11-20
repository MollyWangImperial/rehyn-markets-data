@echo off
title Rehyn Markets data library
cd /d "%~dp0"
echo Rehyn Markets data library
echo Open http://localhost:3040 in your browser.
echo Keep this window open. Closing it stops the site.
echo.
start "" "http://localhost:3040"
python -I server\app.py 3040
pause
