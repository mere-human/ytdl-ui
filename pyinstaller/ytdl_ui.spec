# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import shutil
import sys

project_root = Path(SPECPATH).resolve().parent
if sys.platform != 'win32':
    raise SystemExit('This PyInstaller spec currently targets Windows only.')

yt_dlp_bin = project_root / 'build' / 'yt-dlp-runtime' / 'yt-dlp.exe'
deno_bin = Path(sys.executable).resolve().parent / 'deno.exe'
if not deno_bin.is_file():
    deno_from_path = shutil.which('deno.exe') or shutil.which('deno')
    if deno_from_path:
        deno_bin = Path(deno_from_path)

missing = [str(path) for path in (yt_dlp_bin, deno_bin) if not path.is_file()]
if missing:
    raise SystemExit('Missing bundled runtime(s): ' + ', '.join(missing))

binaries = [
    (str(yt_dlp_bin), '.'),
    (str(deno_bin), '.'),
]

# Windows file metadata (Explorer > Properties > Details).
sys.path.insert(0, str(project_root))
from core import APP_VERSION, version_tuple
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo,
    VarStruct, VSVersionInfo,
)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=version_tuple(APP_VERSION),
        prodvers=version_tuple(APP_VERSION),
    ),
    kids=[
        StringFileInfo([
            StringTable('040904B0', [
                StringStruct('ProductName', 'ytdl-ui'),
                StringStruct('FileDescription', 'ytdl-ui'),
                StringStruct('FileVersion', APP_VERSION),
                StringStruct('ProductVersion', APP_VERSION),
                StringStruct('InternalName', 'ytdl-ui'),
                StringStruct('OriginalFilename', 'ytdl-ui.exe'),
            ]),
        ]),
        VarFileInfo([VarStruct('Translation', [0x0409, 0x04B0])]),
    ],
)

block_cipher = None

a = Analysis(
    [str(project_root / 'main.py')],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=[],
    hiddenimports=['PIL', 'PIL._tkinter_finder'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ytdl-ui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    contents_directory='.',
    version=version_info,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=['yt-dlp.exe', 'deno.exe'],
    name='ytdl-ui',
)
