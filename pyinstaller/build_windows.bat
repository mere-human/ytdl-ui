@echo off
REM Default build: one-file, no console window, using the project .venv if present.

setlocal

set ROOT=%~dp0..
if exist "%ROOT%\.venv\Scripts\python.exe" (
    set PYTHON=%ROOT%\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

echo Using Python: %PYTHON%
%PYTHON% -m pip install pyinstaller
if "%~1"=="" (
    %PYTHON% pyinstaller\build_exe.py --onefile --windowed
) else (
    %PYTHON% pyinstaller\build_exe.py %*
)

endlocal
