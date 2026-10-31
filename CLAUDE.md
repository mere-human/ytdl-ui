# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` is the authoritative contributor guide (conventions, workflow, doc-sync rules) and `TASKS.md` tracks work by priority; read both before larger changes.
This file only adds the commands and big-picture notes.

## Commands

Requires Python 3.11+ (downloads fail on 3.10).
Use the project venv (`.venv`), not system Python.

```bash
pip install -r requirements-dev.txt     # pytest + runtime deps (yt-dlp, Pillow, deno)
python main.py                          # run the app
pytest                                  # all tests (pytest.ini: testpaths=tests, pythonpath=.)
pytest tests/test_formats.py::test_name # single test
.venv\Scripts\python -m pytest          # without activating (Windows)
pyinstaller\build_windows.bat [--clean] # Windows build -> dist/ytdl-ui/ (whole dir is the deliverable)
```

There is no linter configured.

## Architecture

- `main.py` — thin launcher; calls `ui.main()` only when run as a script.
- `core.py` — Tk-free logic: yt-dlp/deno resolution, command-line args, output parsing, thumbnail fetch/decode, cookie settings persistence, logging, `ProcessController` for cancelling the subprocess. Put new testable logic here.
- `ui.py` — Tk widgets and callbacks as **module-level functions and a module-global `root`**, plus `AppState` (`phase`: `init` ↔ `info`, and `busy`). `build_ui(root)` constructs everything, so headless tests can call it on a test root.
- `pyinstaller/` — spec files and build scripts; the build freezes yt-dlp as its own exe and ships Deno beside the app.

Key cross-file behaviors:

- **Threading**: yt-dlp runs in worker threads (`run_check_in_thread`, `run_download_in_thread`).
  Workers must not touch Tk or use cross-thread `root.after`; they call `_post(fn)`, and a main-thread `after` loop (`_pump_ui_queue`) drains the queue (cross-thread `after` is unreliable on macOS).
- **Flow**: Check runs `yt-dlp -F` with `--print THUMB:%(thumbnail)s`; the output is parsed into formats plus a thumbnail URL, and the thumbnail is fetched on the worker thread and shown via Pillow/`ImageTk`.
  Download then streams lines through `run_download_live`; Stop cancels via `ProcessController`, leaving the `.part` file.
- **Tool resolution**: `yt-dlp` and `deno` are looked up next to `sys.executable` (venv) first, then `PATH`.
  yt-dlp is always invoked with explicit args (no `shell=True`), `--js-runtimes deno:<path>` and `--remote-components ejs:github` for YouTube signature solving, with retry/sleep flags for HTTP 429.
- **Cookies**: opt-in browser cookies (`--cookies-from-browser`) or an exported cookie file; only the path (never contents) is persisted by `save_cookie_settings`.
  Chrome/Edge cookie decryption failures on Windows are detected via `is_cookie_read_error`.
- **Tests**: `tests/test_formats.py` covers `core.py`; `tests/test_ui.py` runs headless Tk smoke tests (auto-skipped without a display). Mock `subprocess`/`Popen` rather than calling yt-dlp.

## Conventions worth remembering

- Prefer pytest tests over throwaway `python -c` checks; extract logic from Tk handlers into `core.py` to make it testable.
- Keep docs in sync in the same change: `TASKS.md` markers (`[✓]` / `[~]` / `[ ]`, never `[✓]` with unchecked subtasks), `README.md` for user-facing changes, `AGENTS.md` for architecture/workflow changes.
- Markdown uses Semantic Line Breaks (break after each thought, not mid-sentence).
- Commit only when asked.
