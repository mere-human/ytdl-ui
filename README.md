# ytdl-ui

UI for YouTube downloader ([yt-dlp](https://github.com/yt-dlp/yt-dlp)).

## Roadmap

See **[TASKS.md](TASKS.md)** for the prioritized task list.

## Requirements

### Prebuilt Windows distribution

The Windows distribution includes the app, yt-dlp, and Deno. Users do not need
to install Python, yt-dlp, or Deno. An internet connection is still required
to check and download videos.

FFmpeg is not included. It is needed for formats that require merging separate
audio and video streams; install FFmpeg and add it to `PATH` to use those
formats.

### Running from source or building

- **Python 3.11 or newer.** yt-dlp installs on 3.10 (its packaging minimum),
   but **downloads fail on 3.10**: yt-dlp reports Python 3.10 as deprecated and
   can no longer resolve YouTube signatures on it. Use 3.11+.
   Check your version with `python3 --version`; if it is older than 3.11,
   install a newer Python from [python.org](https://www.python.org/downloads/)
   or your package manager (e.g. `brew install python@3.12`).

No global JavaScript runtime is required when running from source: YouTube
downloads need one to solve signature challenges, and it is installed into the
venv for you. The [`deno`](https://pypi.org/project/deno/) package (a
redistribution of the Deno binary) is listed in `requirements.txt`, and the
app points yt-dlp at the venv's copy automatically. The Windows build includes
a standalone Deno executable in its output directory.

## Installation

Use a virtual environment so dependencies stay isolated from your system Python.

Create and activate a venv with a Python 3.11+ interpreter:

```bash
# Create the venv (use the specific interpreter, e.g. python3.12, if `python3` is older)
python3.12 -m venv .venv

# Activate it
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows (PowerShell/cmd)
```

Confirm the venv uses Python 3.11+:

```bash
python --version
```

Make sure `pip` is available in the venv. Most venvs include it, but if
`python -m pip --version` fails with `No module named pip`, bootstrap it:

```bash
python -m ensurepip --upgrade
```

Then install dependencies into the activated venv:

```bash
pip install -r requirements.txt
```

This installs [yt-dlp](https://github.com/yt-dlp/yt-dlp) inside the venv,
plus [Pillow](https://pypi.org/project/Pillow/) so JPEG/WebP thumbnails can
be shown in the UI (Tk's built-in image loader does not decode those formats).
Alternatively, install yt-dlp via your system package manager — see the
[yt-dlp installation guide](https://github.com/yt-dlp/yt-dlp#installation).

Verify yt-dlp is available:

```bash
yt-dlp --version
```

Deactivate the venv when done with `deactivate`.

## Usage

1. Start the app: `python main.py`
2. Paste the video URL. Example
   - https://www.youtube.com/watch?v=dQw4w9WgXcQ
   - https://www.youtube.com/watch?v=y6120QOlsfU
3. Press "Check"
4. (Optional) Pick a format from the **Format** dropdown that appears — leave
   it on "best (default)" to let yt-dlp choose the best quality automatically.
   A thumbnail preview appears next to the info panel when the check succeeds.
5. (Optional) Choose where to save via the **Folder** row — it defaults to your
   Downloads folder (or the current directory if that doesn't exist). Click
   **Browse...** to pick another folder.
6. Press "Download"
7. Find the file in the selected folder.

To use your browser's YouTube session, enable **Use browser cookies** and
choose Chrome, Edge, Firefox, or Brave. yt-dlp reads cookies from that browser
for both checking and downloading. The app remembers only the opt-in and
browser selection; it does not store cookie data. Close the browser first if
yt-dlp reports that it cannot read the browser's cookie database.

To cancel a download in progress, press **Stop** (it appears next to the
Download button while downloading). yt-dlp keeps the partially downloaded
`.part` file on disk and the info panel shows its path; the app returns to the
format list so you can adjust the format and retry without checking again.

### Rate limiting (HTTP 429)

YouTube may rate-limit requests with `HTTP Error 429: Too Many Requests`.
The app automatically retries with backoff and sleeps between requests to
reduce this. If you still get rate limited, the info panel shows guidance:

- Wait a few minutes before retrying.
- If YouTube asks you to sign in or solve a CAPTCHA, enable **Use browser
   cookies** after completing the challenge in your browser.
- Update yt-dlp. For a prebuilt bundle, rebuild it or replace the bundled
   `yt-dlp.exe`; updating a separate Python installation does not update it.
- Avoid checking many URLs in quick succession.

## Development

Set up the venv as described in [Installation](#installation) (Python 3.11+),
then, with it activated:

```bash
pip install -r requirements.txt
python main.py
```

Agent and contributor notes: **[AGENTS.md](AGENTS.md)**.

### Tests

Unit tests use [pytest](https://pytest.org). With the venv **activated** (see
[Installation](#installation)), install the dev dependencies and run the suite
from the repo root:

```bash
pip install -r requirements-dev.txt   # pulls in pytest (and runtime deps)
pytest
```

### Building the Windows distribution (PyInstaller)

From the project root, with dependencies installed in the project venv, run:

```bash
pyinstaller\build_windows.bat
```

The script uses `.venv` when available, installs PyInstaller into that
environment, freezes the installed yt-dlp package as a standalone executable,
and builds a Windows directory bundle containing yt-dlp and Deno. To rebuild
from a clean PyInstaller cache, pass `--clean`:

```bash
pyinstaller\build_windows.bat --clean
```

The complete distributable is `dist/ytdl-ui/`. Distribute the whole directory
(for example, as a zip); users run `ytdl-ui.exe` inside it. Do not distribute
the app executable by itself.

Users can update yt-dlp independently before an in-app updater is available:
close the app and replace `dist/ytdl-ui/yt-dlp.exe` with the current official
Windows standalone executable from the
[yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases), keeping the
filename unchanged. A future app build will replace this manual update with
the version bundled in that build.

The current build helper targets Windows only. Do not commit `dist/` or
`build/` artifacts produced by PyInstaller.


Run tests on the same Python 3.11+ interpreter the app uses — the venv's. When
the venv is activated, `python`, `pip`, and `pytest` all resolve to it; to run
without activating, call the venv binaries explicitly:

```bash
.venv/bin/python -m pytest            # macOS / Linux
# .venv\Scripts\python -m pytest      # Windows
```

Avoid a bare `python3 -m pytest` unless the venv is activated — outside the
venv it may run a different system Python and won't see the installed deps.

`main.py` is a thin launcher for `ui.py`; importing either module does not
create a window. Tk construction lives in `ui.build_ui()`, while reusable
Tk-free behavior lives in `core.py`. Tests live in `tests/`:
`test_formats.py` covers core logic and `test_ui.py` runs headless Tk smoke
tests for widget enable/disable behavior (auto-skipped if Tk has no display).
