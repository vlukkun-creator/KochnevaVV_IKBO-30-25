@echo off
cd /d "%~dp0"
call :run --log logs\stage4.xml --script tests\scripts\stage4.emu
call :run --vfs vfs_deep --script tests\scripts\stage3_deep.emu
goto :eof

:run
echo.
echo === emulator %*
py src\emulator.py %EMU_FLAGS% %* < NUL
echo --- exit code: %ERRORLEVEL%
goto :eof
