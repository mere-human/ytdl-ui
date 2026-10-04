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
- Prefer the **venv's** `yt-dlp` and `deno` (resolved next to `sys.executable`),
  falling back to `PATH`; this keeps the toolchain project-local.
- **Thumbnails**: the format check passes `--print THUMB:%(thumbnail)s` with
  `-F`. The URL is fetched with `urllib` on the worker thread; Pillow decodes
  JPEG/WebP and the main thread shows it in a `ttk.Label` via `ImageTk`.
- **JS runtime**: YouTube signature/challenge solving needs a JavaScript
  runtime. `deno` is a `requirements.txt` dependency (installed into the venv);
  `main.py` passes `--js-runtimes deno:<venv>/bin/deno` explicitly so it works
  regardless of PATH. yt-dlp only auto-enables deno, and Node additionally
  needs `--remote-components ejs:github`, so deno is the simpler choice.
- For PyInstaller builds, consider bundling yt-dlp (and deno) or documenting how users obtain them alongside the exe.

### UI (Tkinter)

- Keep using `ttk` widgets for native look.
- Long-running work **must** run off the main thread (`threading.Thread`, `subprocess.Popen` + polling, or `asyncio` only if the whole app is refactored for it).
- Update UI from worker threads via `root.after(...)` — never call Tk widgets directly from background threads.
- Replace plain `ttk.Label` for long output with `Text` + `Scrollbar` (or `ScrolledText`) for scroll and wrap.
- Preserve existing layout intent: URL row + expandable info area with grid weights for resize.

## Development

### Prerequisites

- Python 3.11+ — required (pinned in `.python-version`); downloads fail on 3.10.
  See the [README](README.md#prerequisites) for the full rationale.
  (You may use features like `str | None` if typing is added.)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) installed and on PATH

### Run locally

```bash
python main.py
```

### Dependencies

Runtime dependencies are listed in `requirements.txt`. When adding third-party packages:

- Add to `requirements.txt` (or migrate to `pyproject.toml` if the project outgrows a single file)
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

Use **pytest**. Place tests in `tests/`. Test/dev dependencies live in
`requirements-dev.txt` (keeps runtime `requirements.txt` minimal); install and
run **inside the activated venv** (its Python 3.11+ interpreter — not a system
`python3`, which may differ and won't have the deps):

```bash
pip install -r requirements-dev.txt
pytest                       # activated venv
# or, without activating:
.venv/bin/python -m pytest   # Windows: .venv\Scripts\python -m pytest
```

If the venv has no pip (`No module named pip`), bootstrap it with
`python -m ensurepip --upgrade` before installing.

`main.py` guards its Tk construction under `if __name__ == "__main__":`; the UI
is built in `build_ui(root)` and `main()` owns the event loop, so the module
imports in tests without launching a window, and `build_ui` can be called on a
headless root to smoke-test widget behavior. Keep new logic in pure, Tk-free
functions (as with `parse_formats`, `format_id_from_label`, `is_rate_limited`,
`is_valid_url`, `output_args`, `parse_thumbnail_url`, `fit_thumbnail_size`,
`fetch_thumbnail_bytes`, `decode_thumbnail`) so it stays unit-testable. Coverage lives in
`tests/test_formats.py` (pure logic) and `tests/test_ui.py` (headless Tk widget
state, e.g. that `set_busy` disables the format picker).

Add tests alongside new features; do not leave behavior untested when logic is extractable from Tk callbacks.

**Prefer tests over throwaway verification.** When you need to confirm behavior,
write a `pytest` test in `tests/` rather than a one-off `python -c "..."`
snippet or a scratch script. Extract the logic into a pure, Tk-free function so
it can be asserted on, then keep the test as regression coverage. Reserve
ad-hoc snippets for genuinely un-testable environment probing (e.g. checking
whether an interpreter has `pip`); never use them as a substitute for a test of
project logic.

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
3. Extract testable logic from Tk handlers and cover it with `pytest` tests (prefer tests over ad-hoc `python -c` snippets).
4. After UI changes, also verify manually where tests can't reach: resize window, empty URL, invalid URL, long format list.
5. Do not add markdown docs the user did not request (except maintaining [TASKS.md](TASKS.md), this file, and README when behavior changes).
6. **Keep docs in sync** — after completing a task or fixing a bug, update the relevant docs in the same change:
   - Mark items in **[TASKS.md](TASKS.md)** using its status markers — `[✓]`
     done, `[~]` in progress, `[ ]` not started — and **never mark a task `[✓]`
     while any of its subtasks are unchecked** (use `[~]`). Add new items if
     work was unplanned.
   - Update **[README.md](README.md)** when user-facing behavior, prerequisites, or usage steps change.
   - Update this file (**AGENTS.md**) when architecture, conventions, or workflow rules change.

## Out of scope unless asked

- Web UI or Electron rewrite
- Supporting sites beyond what yt-dlp handles
- Bundling ffmpeg unless required for chosen formats
- Force push, git config changes, or commits without user request
