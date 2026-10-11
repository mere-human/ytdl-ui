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
