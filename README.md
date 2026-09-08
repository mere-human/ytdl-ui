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
4. Press "Download"
5. Find the file in the same folder as the script.

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
