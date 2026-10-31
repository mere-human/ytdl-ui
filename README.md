# ytdl-ui

A small desktop GUI for the [yt-dlp](https://github.com/yt-dlp/yt-dlp) video downloader.
Paste a URL, check what's available, pick a format and download.

- [Windows app (prebuilt)](#windows-app-prebuilt)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- Roadmap: **[TASKS.md](TASKS.md)** · Contributor and agent notes: **[AGENTS.md](AGENTS.md)**

## Windows app (prebuilt)

The release is a zip (`ytdl-ui.zip`) containing a `ytdl-ui` folder.
It bundles the app together with yt-dlp and Deno,
so you don't need to install Python, yt-dlp or Deno.

1. Extract the whole zip somewhere you can write to,
   for example `C:\Users\<you>\Apps\ytdl-ui`.
   Don't run it from inside the zip.
2. Run `ytdl-ui.exe` from the extracted `ytdl-ui` folder.
   Keep all files together:
   the app needs `yt-dlp.exe`, `deno.exe` and the other files next to it,
   so copying `ytdl-ui.exe` alone won't work
   (create a shortcut instead).
3. If Windows SmartScreen warns about an unrecognized app,
   choose **More info → Run anyway** (the exe is not code-signed).

Notes:

- An internet connection is required to check and download videos.
- **FFmpeg is not included.**
  It's needed to merge separate video and audio streams
  and to convert to MP3/M4A/Opus or MP4/MKV.
  Install [FFmpeg](https://ffmpeg.org/download.html) and add it to `PATH`
  to use those formats.
- **Updating yt-dlp.**
  When YouTube changes, an old yt-dlp may stop working.
  Close the app and replace `yt-dlp.exe` in the app folder
  with the latest `yt-dlp.exe` from the
  [yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases),
  keeping the same filename.
  A newer ytdl-ui release also ships a newer yt-dlp.
  The status bar shows the yt-dlp version in use.
- **Uninstalling.** Delete the app folder.
  Settings are stored in `%LOCALAPPDATA%\ytdl-ui\settings.json`
  and logs in `%TEMP%\ytdl-ui\`; delete those too if you like.

## Usage

1. Start the app
   (`ytdl-ui.exe`, or `python main.py` when [running from source](#running-from-source)).
2. Paste a video URL, for example
   `https://www.youtube.com/watch?v=dQw4w9WgXcQ`.
3. Press **check**.
   Video info and a thumbnail preview appear when the check succeeds,
   and the button changes to **download**.
4. (Optional) Choose what to download in the **Format** row:
   - **Type**: Video + Audio (default), Video only or Audio only.
   - **Quality**: Best (default), the resolutions this video offers (e.g. 1080p) or Lowest;
     for audio: Best, Medium or Low.
   - **Container**: Auto (default), MP4 or MKV for video;
     Original, MP3, M4A or Opus for audio.
     Conversions need FFmpeg.
   - The estimated download size is shown next to the dropdowns
     ("size unknown" when yt-dlp doesn't report one).
   - Tick **Subtitles** and pick a language to also download captions
     (manual tracks first, then auto-generated ones marked "(auto)").
   - **Show all formats...** opens the raw yt-dlp format table.
     Double-click a row (or press **Use selected format**) to download exactly that format;
     a video-only pick automatically gets the best audio merged in.
     **Clear** returns to the presets.
5. (Optional) Choose where to save in the **Folder** row.
   It defaults to your Downloads folder
   (or the current directory if that doesn't exist);
   **Browse...** picks another folder.
6. Press **download**, then find the file in the selected folder.

To cancel, press **Stop** (next to the download button while a download runs).
yt-dlp keeps the partial `.part` file and the info panel shows its path.
The app returns to the format list,
so you can adjust the format and retry without checking again.

Editing the URL after a check clears the results
and turns the button back into **check** for the new URL.

The status bar at the bottom shows the app version (CalVer, `YYYY.MM.DD`)
and the yt-dlp version in use.

### Browser cookies

Some videos need your YouTube session
(age-restricted or members-only videos, or when YouTube asks you to sign in).
Enable **Use browser cookies** and choose a browser.
On Windows, Firefox works best.
The app remembers this choice between sessions.

Chrome and Edge cookies often can't be decrypted on Windows
(see [yt-dlp#10927](https://github.com/yt-dlp/yt-dlp/issues/10927)).
Use an exported cookie file instead:

1. Install a "Get cookies.txt" browser extension, such as
   [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc).
2. Sign in to YouTube in Chrome or Edge,
   then use the extension to export the site's cookies to a text file.
3. Enable **Use browser cookies**, choose **Browse...** in the Browser dropdown
   and select the exported file.
   It's used for both checking and downloading.

Only the cookie file's path is saved, never its contents.
Keep the file private: it gives access to your account.

## Troubleshooting

### Rate limiting (HTTP 429)

YouTube may answer with `HTTP Error 429: Too Many Requests`.
The app already retries with backoff and pauses between requests.
If it still happens:

- Wait a few minutes before retrying.
- If YouTube asks you to sign in or solve a CAPTCHA,
  enable [browser cookies](#browser-cookies).
- Update yt-dlp
  (prebuilt app: see [Updating yt-dlp](#windows-app-prebuilt);
  from source: `pip install -U yt-dlp` in the venv).
- Avoid checking many URLs in quick succession.

### Logs

Each run writes a log to `ytdl-ui-<pid>.log` in the system temp folder
(`%TEMP%\ytdl-ui\` on Windows).
It's useful to attach when reporting a problem.

## Development

### Prerequisites

- **Python 3.11 or newer** (see `.python-version`).
  yt-dlp installs on 3.10, but downloads fail there:
  yt-dlp treats 3.10 as deprecated and can no longer solve YouTube signatures on it.
  Check with `python --version`;
  get a newer Python from [python.org](https://www.python.org/downloads/)
  or your package manager (e.g. `brew install python@3.12`).
- No global JavaScript runtime is needed.
  YouTube signature solving needs one,
  so the [`deno`](https://pypi.org/project/deno/) package in `requirements.txt`
  installs Deno into the venv and the app points yt-dlp at it.
- FFmpeg on `PATH` for merging and conversions (optional).

### Running from source

Use a virtual environment so dependencies stay out of your system Python:

```bash
python3.12 -m venv .venv          # any 3.11+ interpreter
source .venv/bin/activate         # macOS / Linux
# .venv\Scripts\activate          # Windows (PowerShell / cmd)

python --version                  # confirm 3.11+
pip install -r requirements.txt   # yt-dlp, deno, Pillow
python main.py
```

If `pip` is missing in the venv (`No module named pip`),
run `python -m ensurepip --upgrade` first.

`requirements.txt` installs yt-dlp, Deno,
and [Pillow](https://pypi.org/project/Pillow/) for JPEG/WebP thumbnails
(Tk's built-in image loader can't decode those).
The app looks for `yt-dlp` and `deno` next to the running Python first
(the venv), then on `PATH`,
so a system-wide yt-dlp also works if it isn't in the venv.

### Tests

Tests use [pytest](https://pytest.org).
From the repo root, with the venv activated:

```bash
pip install -r requirements-dev.txt   # pytest + runtime deps
pytest
```

Without activating, call the venv's interpreter explicitly
(`.venv/bin/python -m pytest` on macOS/Linux,
`.venv\Scripts\python -m pytest` on Windows).
A bare `python3 -m pytest` outside the venv may use a different Python
that lacks the dependencies.

- `tests/test_formats.py` covers the Tk-free logic in `core.py`.
- `tests/test_ui.py` runs headless Tk smoke tests
  (skipped automatically when Tk has no display).

### Code layout

- `main.py` — thin launcher for `ui.py`.
- `ui.py` — Tk widgets and callbacks; the window is built by `ui.build_ui()`.
- `core.py` — Tk-free logic: tool resolution, yt-dlp arguments, output parsing,
  thumbnails, cookie settings, logging, process control.
  `core.APP_VERSION` is the single source of the app version.
- `pyinstaller/` — Windows build script and spec.

Importing `main` or `ui` doesn't create a window.
See [AGENTS.md](AGENTS.md) for conventions and workflow.

### Building the Windows release (PyInstaller)

On Windows, from the repo root, with dependencies installed in `.venv`:

```bash
pyinstaller\build_windows.bat           # add --clean to drop the PyInstaller cache
```

The script uses `.venv` when present, installs PyInstaller into it,
freezes the installed yt-dlp as a standalone `yt-dlp.exe`,
and builds the directory bundle `dist/ytdl-ui/`
with `ytdl-ui.exe`, `yt-dlp.exe` and `deno.exe`.
The exe's file properties carry `APP_VERSION`.

The whole `dist/ytdl-ui/` folder is the deliverable; never ship `ytdl-ui.exe` alone.
The build doesn't create the zip; make it yourself, for example:

```powershell
Compress-Archive -Path dist\ytdl-ui -DestinationPath dist\ytdl-ui.zip -Force
```

The build helper is Windows-only.
`build/` and `dist/` are git-ignored; don't commit them.
