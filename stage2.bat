@echo off
cd /d "%~dp0"
call :run
call :run --script tests\scripts\stage2.emu
call :run --log logs\stage2.xml --script tests\scripts\stage2.emu
call :run --vfs vfs_minimal --script tests\scripts\stage2.emu
call :run --vfs vfs_files --log logs\stage2_all.xml --script tests\scripts\stage2.emu
call :run --script tests\scripts\no_such_script.emu
call :run --log Z:\no_such_drive\log.xml --script tests\scripts\stage2.emu
goto :eof

:run
echo.
echo === emulator %*
py src\emulator.py %EMU_FLAGS% %* < NUL
echo --- exit code: %ERRORLEVEL%
goto :eof
