@echo off
cd /d "%~dp0"
set EMU_FLAGS=--headless
call stage2.bat
call stage3.bat
call stage4.bat
call stage5.bat
