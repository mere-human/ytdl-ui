# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import shutil
import sys

project_root = Path(SPECPATH).resolve().parent
is_win = sys.platform == 'win32'
if not (is_win or sys.platform == 'darwin'):
    raise SystemExit('This PyInstaller spec targets Windows and macOS only.')

exe_suffix = '.exe' if is_win else ''
yt_dlp_dir = project_root / 'build' / 'yt-dlp-runtime'
yt_dlp_bin = yt_dlp_dir / f'yt-dlp{exe_suffix}'
if not is_win:
    yt_dlp_dir = yt_dlp_dir / 'yt-dlp'  # one-dir build
    yt_dlp_bin = yt_dlp_dir / 'yt-dlp'
deno_bin = Path(sys.executable).absolute().parent / f'deno{exe_suffix}'
if not deno_bin.is_file():
    deno_from_path = shutil.which('deno')
    if deno_from_path:
        deno_bin = Path(deno_from_path)

missing = [str(path) for path in (yt_dlp_bin, deno_bin) if not path.is_file()]
if missing:
    raise SystemExit('Missing bundled runtime(s): ' + ', '.join(missing))

binaries = [(str(deno_bin), '.')]
datas = []
if is_win:
    binaries.append((str(yt_dlp_bin), '.'))
else:
    datas.append((str(yt_dlp_dir), 'yt-dlp-runtime'))

sys.path.insert(0, str(project_root))
from core import APP_VERSION, version_tuple

# Windows file metadata (Explorer > Properties > Details).
version_info = None
if is_win:
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
    datas=datas,
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
    upx=is_win,
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
    upx=is_win,
    upx_exclude=['yt-dlp.exe', 'deno.exe', 'yt-dlp', 'deno'],
    name='ytdl-ui',
)

if sys.platform == 'darwin':
    # Double-clicking a bare Unix executable opens Terminal, so ship a .app.
    app = BUNDLE(
        coll,
        name='ytdl-ui.app',
        icon=None,
        bundle_identifier='com.github.mere-human.ytdl-ui',
        info_plist={
            'CFBundleName': 'ytdl-ui',
            'CFBundleDisplayName': 'ytdl-ui',
            'CFBundleShortVersionString': APP_VERSION,
            'CFBundleVersion': APP_VERSION,
            'NSHighResolutionCapable': True,
        },
    )
