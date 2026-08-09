# ytdl-ui

UI for YouTube downloader ([yt-dlp](https://github.com/yt-dlp/yt-dlp)).

## Roadmap

See **[TASKS.md](TASKS.md)** for the prioritized task list.

## Prerequisites

- Python 3.10+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) on your PATH

## Installation

```bash
pip install -r requirements.txt
```

This installs [yt-dlp](https://github.com/yt-dlp/yt-dlp). Alternatively, install it via your system package manager — see the [yt-dlp installation guide](https://github.com/yt-dlp/yt-dlp#installation).

Verify yt-dlp is available:

```bash
yt-dlp --version
```

## Usage

1. Start the app: `python main.py`
2. Paste the video URL e.g. https://www.youtube.com/watch?v=dQw4w9WgXcQ
3. Press "Check"
4. Press "Download"
5. Find the file in the same folder as the script.

## Development

```bash
pip install -r requirements.txt
python main.py
```

Agent and contributor notes: **[AGENTS.md](AGENTS.md)**.
