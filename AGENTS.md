# Agent guide

Guidance for AI coding agents working on **ytdl-ui** — a cross-platform desktop UI for downloading YouTube videos via **yt-dlp**.

## Project overview

| | |
|---|---|
| **Purpose** | Simple GUI wrapper around the yt-dlp CLI for checking formats and downloading videos |
| **Stack** | Python 3, Tkinter (`ttk`), subprocess |
| **License** | MIT |
| **Repo** | https://github.com/mere-human/ytdl-ui |
| **Entry point** | `main.py` |

The app is early-stage. Current flow: enter URL → **check** (lists formats via `-F`) → **download**. The UI is synchronous today and blocks during subprocess calls.

Work is tracked in **[TASKS.md](TASKS.md)** (grouped by priority). Distribution target: **PyInstaller** standalone executables for Windows, macOS, and Linux.

## Architecture

```
main.py          # entry point (may split as complexity grows)
```

Current state machine in `run_btn_press`:

```
init  --[check]-->  info  --[download]-->  init
  ^                      |
  +--------[error]-------+
```

Agents may split into modules when it improves clarity (e.g. `ui/`, `downloader/`, `models/`). Prefer incremental refactors tied to a feature, not big-bang rewrites.

### Downloader backend

- Use **`yt-dlp`** as the only backend (not youtube-dl).
- Invoke via `subprocess` with explicit args; avoid shell=True.
- Decode stdout/stderr as text (`encoding="utf-8", errors="replace"`).
- Assume yt-dlp is on `PATH` for dev; document install steps in README when changed.
- For PyInstaller builds, consider bundling yt-dlp or documenting how users obtain it alongside the exe.

### UI (Tkinter)

- Keep using `ttk` widgets for native look.
- Long-running work **must** run off the main thread (`threading.Thread`, `subprocess.Popen` + polling, or `asyncio` only if the whole app is refactored for it).
- Update UI from worker threads via `root.after(...)` — never call Tk widgets directly from background threads.
- Replace plain `ttk.Label` for long output with `Text` + `Scrollbar` (or `ScrolledText`) for scroll and wrap.
- Preserve existing layout intent: URL row + expandable info area with grid weights for resize.

## Development

### Prerequisites

- Python 3.10+ (use features like `str | None` if typing is added)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) installed and on PATH

### Run locally

```bash
python main.py
```

### Dependencies

There is no `requirements.txt` yet. When adding third-party packages:

- Add `requirements.txt` (or `pyproject.toml` if the project outgrows a single file)
- Pin reasonable versions
- Keep runtime deps minimal (stdlib + yt-dlp if ever embedded as a library — today it's CLI-only)

### PyInstaller

When packaging work begins:

- Add a `.spec` or documented build script
- Test on each target OS; Tkinter + subprocess paths differ per platform
- Do not commit large `dist/` or `build/` artifacts (already gitignored)

## Testing

Full test coverage is expected over time:

| Layer | Approach |
|---|---|
| **Core logic** | Unit tests: format parsing, state transitions, URL validation, command-line arg building |
| **Downloader** | Mock `subprocess` / `Popen`; test success, non-zero exit, timeout, partial output |
| **UI** | Integration or smoke tests where practical (e.g. `pytest` + threading checks); avoid brittle pixel tests |

Use **pytest**. Place tests in `tests/`. Run with:

```bash
pytest
```

Add tests alongside new features; do not leave behavior untested when logic is extractable from Tk callbacks.

## Code conventions

- **Minimize scope** — small, focused diffs; match existing style in `main.py`.
- **No over-engineering** — no premature abstractions; split files when a module has a clear responsibility.
- **Comments** — only for non-obvious behavior (threading, yt-dlp quirks).
- **Globals** — reduce `global current_state` over time; prefer a small class or dataclass for app state.
- **Errors** — surface yt-dlp stderr to the user; reset state to `init` on failure.
- **Commits** — only when the user asks; follow repo message style (short imperative: "Add state", "Integrate youtube-dl").

## Known issues

Outstanding fixes are listed as open items in **[TASKS.md](TASKS.md)** (especially P1–P3). When an item is completed, mark it there and remove or update any stale notes here.

## Agent workflow

1. Read **[TASKS.md](TASKS.md)** and this file before large changes.
2. Prefer one task (or a coherent subset) from the highest-priority open group.
3. Extract testable logic from Tk handlers when adding tests.
4. After UI changes, verify manually: resize window, empty URL, invalid URL, long format list.
5. Do not add markdown docs the user did not request (except maintaining [TASKS.md](TASKS.md), this file, and README when behavior changes).

## Out of scope unless asked

- Web UI or Electron rewrite
- Supporting sites beyond what yt-dlp handles
- Bundling ffmpeg unless required for chosen formats
- Force push, git config changes, or commits without user request
