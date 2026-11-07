@echo off
rem Catch them! (docs/kids.md): starts the game's server and opens it in the browser. Closing this window ends it.
rem Every game is kept in %USERPROFILE%\terrarium-kids.
cd /d "%~dp0..\sim"
uv run --extra cpu python -m terrarium.kidsserve --brain "%USERPROFILE%\terrarium-kids\brain.pt" --keep "%USERPROFILE%\terrarium-kids" --open
if errorlevel 1 pause
