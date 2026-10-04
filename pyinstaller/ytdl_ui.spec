# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[1]
venv_root = project_root / '.venv'

# Include the project-local yt-dlp executable in the bundle so the app can run
# even when Python is installed elsewhere. Prefer the venv copy, fall back to
# PATH, and always keep the build self-contained for GUI use.
if sys.platform.startswith('win'):
    yt_dlp_bin = venv_root / 'Scripts' / 'yt-dlp.exe'
else:
    yt_dlp_bin = venv_root / 'bin' / 'yt-dlp'

binaries = []
if yt_dlp_bin.exists():
    binaries = [(str(yt_dlp_bin), 'yt-dlp.exe' if sys.platform.startswith('win') else 'yt-dlp')]

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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ytdl-ui',
)
