@echo off
cd /d "%~dp0"
call :run --log logs\stage5.xml --script tests\scripts\stage5.emu
call :run --vfs vfs_files --script tests\scripts\stage5.emu
goto :eof

:run
echo.
echo === emulator %*
py src\emulator.py %EMU_FLAGS% %* < NUL
echo --- exit code: %ERRORLEVEL%
goto :eof
