@echo off
cd /d "%~dp0"
set PYTHONPATH=src
py -m unittest discover -s tests -v
