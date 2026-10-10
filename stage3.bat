@echo off
cd /d "%~dp0"
call :run --script tests\scripts\stage3_minimal.emu
call :run --vfs vfs_minimal --script tests\scripts\stage3_minimal.emu
call :run --vfs vfs_files --script tests\scripts\stage3_files.emu
call :run --vfs vfs_deep --script tests\scripts\stage3_deep.emu
call :run --vfs vfs_no_such_dir --script tests\scripts\stage3_minimal.emu
call :run --vfs vfs_not_dir.txt --script tests\scripts\stage3_minimal.emu
call :run --script tests\scripts\stage3_all.emu
goto :eof

:run
echo.
echo === emulator %*
py src\emulator.py %EMU_FLAGS% %* < NUL
echo --- exit code: %ERRORLEVEL%
goto :eof
