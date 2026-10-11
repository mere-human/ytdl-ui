@echo off
REM Build the Windows directory bundle, using the project .venv if present.

setlocal

set ROOT=%~dp0..
pushd "%ROOT%"
if exist "%ROOT%\.venv\Scripts\python.exe" (
    set PYTHON=%ROOT%\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

echo Using Python: %PYTHON%
%PYTHON% -m pip install pyinstaller
if errorlevel 1 (
    echo Failed to install PyInstaller.
    popd
    exit /b 1
)

%PYTHON% pyinstaller\build_exe.py %*
set BUILD_EXIT=%ERRORLEVEL%

popd
endlocal & exit /b %BUILD_EXIT%
