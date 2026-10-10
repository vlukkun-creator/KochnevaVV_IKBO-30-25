@echo off
cd /d "%~dp0"
set PYTHONPATH=src
python -m unittest discover -s tests -v
