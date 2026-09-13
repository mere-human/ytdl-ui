# ytdl-ui

UI for YouTube downloader ([yt-dlp](https://github.com/yt-dlp/yt-dlp)).

## Roadmap

See **[TASKS.md](TASKS.md)** for the prioritized task list.

## Prerequisites

- **Python 3.11 or newer.** yt-dlp installs on 3.10 (its packaging minimum),
  but **downloads fail on 3.10**: yt-dlp reports Python 3.10 as deprecated and
  can no longer resolve YouTube signatures on it. Use 3.11+.
  Check your version with `python3 --version`; if it is older than 3.11,
  install a newer Python from [python.org](https://www.python.org/downloads/)
  or your package manager (e.g. `brew install python@3.12`).

No global JavaScript runtime is required: YouTube downloads need one to solve
signature challenges, and it is installed into the venv for you. The
[`deno`](https://pypi.org/project/deno/) package (a redistribution of the Deno
binary) is listed in `requirements.txt`, and the app points yt-dlp at the
venv's copy automatically.

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

This installs [yt-dlp](https://github.com/yt-dlp/yt-dlp) inside the venv.
Alternatively, install yt-dlp via your system package manager — see the
[yt-dlp installation guide](https://github.com/yt-dlp/yt-dlp#installation).

Verify yt-dlp is available:

```bash
yt-dlp --version
```

Deactivate the venv when done with `deactivate`.

## Usage

1. Start the app: `python main.py`
2. Paste the video URL e.g. https://www.youtube.com/watch?v=dQw4w9WgXcQ
3. Press "Check"
4. (Optional) Pick a format from the **Format** dropdown that appears — leave
   it on "best (default)" to let yt-dlp choose the best quality automatically.
5. (Optional) Choose where to save via the **Folder** row — it defaults to your
   Downloads folder (or the current directory if that doesn't exist). Click
   **Browse...** to pick another folder.
6. Press "Download"
7. Find the file in the selected folder.

To cancel a download in progress, press **Stop** (it appears next to the
Download button while downloading). yt-dlp keeps the partially downloaded
`.part` file on disk and the info panel shows its path; the app returns to the
format list so you can adjust the format and retry without checking again.

### Rate limiting (HTTP 429)

YouTube may rate-limit requests with `HTTP Error 429: Too Many Requests`.
The app automatically retries with backoff and sleeps between requests to
reduce this. If you still get rate limited, the info panel shows guidance:

- Wait a few minutes before retrying.
- Update yt-dlp: `pip install -U yt-dlp`
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

Run tests on the same Python 3.11+ interpreter the app uses — the venv's. When
the venv is activated, `python`, `pip`, and `pytest` all resolve to it; to run
without activating, call the venv binaries explicitly:

```bash
.venv/bin/python -m pytest            # macOS / Linux
# .venv\Scripts\python -m pytest      # Windows
```

Avoid a bare `python3 -m pytest` unless the venv is activated — outside the
venv it may run a different system Python and won't see the installed deps.

`main.py` builds its UI in `build_ui()` (called from `main()`, guarded by
`if __name__ == "__main__":`), so tests import it without launching a window.
Tests live in `tests/`: `test_formats.py` covers the pure logic (parsing,
URL/format validation, output paths) and `test_ui.py` runs headless Tk smoke
tests for widget enable/disable behavior (auto-skipped if Tk has no display).
