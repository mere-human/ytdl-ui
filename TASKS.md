# Task list

Prioritized backlog for **ytdl-ui**. Agents: pick the next open item (or a coherent subset) from the highest priority group that has unfinished work.

**Status markers:**
- `[ ]` — not started
- `[~]` — in progress (work begun, but at least one subtask is still open)
- `[✓]` — done (only mark a task `[✓]` when **every** subtask is also `[✓]`)

Never mark a parent task `[✓]` while any of its subtasks remain unchecked — use
`[~]` instead until they are all done.

See also: [Agent guide](AGENTS.md) · [README](README.md)

---

## P1 — Foundation

Core backend and UI responsiveness. Unblocks everything else.

- [✓] **Migrate to yt-dlp**
  - [✓] Replace all `youtube-dl` CLI invocations with `yt-dlp`
  - [✓] Update README and user-facing strings
  - [✓] Document yt-dlp install requirement (on PATH for dev)
- [✓] **Real download flow**
  - [✓] Remove `--help` placeholder; download with selected URL (and format when available)
  - [✓] Decode subprocess stdout/stderr as UTF-8 text before showing in UI
  - [✓] Reset app state to `init` on failure; surface stderr to the user
- [✓] **Graceful error when yt-dlp is missing**
  - [✓] Catch `FileNotFoundError` and show actionable message in the info panel
  - [✓] Add `requirements.txt` with yt-dlp dependency
- [✓] **Non-blocking UI**
  - [✓] Run check and download off the main thread (`threading` or `Popen` + polling)
  - [✓] Update UI only via `root.after(...)` from worker threads
  - [✓] Keep window responsive during long operations
  - [✓] Stream live status output during download (`Popen` line-by-line)
  - [✓] Update UI with the status output live
- [✓] **Bug: HTTP 429 on URL check**
  - [✓] Reproduce: paste a YouTube URL and check — `Unable to download webpage: HTTP Error 429: Too Many Requests`
  - [✓] Investigate yt-dlp mitigations (update yt-dlp, cookies from browser, retries/sleep, user-agent)
  - [✓] Surface clear, actionable guidance in the UI when rate-limited
- [✓] **Bug: UI is not focused after start**
- [✓] **Use a virtual environment**
  - [✓] Document creating/activating a venv in README (`python -m venv .venv`)
  - [✓] Note the required Python version — yt-dlp needs a newer Python than 3.10 for downloads to work; pin/document the minimum (3.11+; also pinned in `.python-version`)
  - [✓] Ensure `pip install -r requirements.txt` targets the venv
  - Moved up from P6: without this, downloads fail on Python 3.10 and can't be tested.

---

## P2 — Core download workflow

Minimum viable “check → pick → download” experience.

- [✓] **Format selection**
  - [✓] Parse `yt-dlp -F` output into a selectable list
  - [✓] Let user pick a format before download
  - [✓] Pass chosen format id to the download command
- [✓] **Output folder**
  - [✓] Add browse control for download directory
  - [✓] Pass output path to yt-dlp (`-o` or equivalent)
  - [✓] Sensible default (e.g. current directory or user Downloads)
  - [✓] Show the currently selected folder in UI
- [✓] **Download button state**
  - [✓] Disable when URL is empty or invalid
  - [✓] Disable while check or download is in progress
  - [✓] Re-enable appropriately on success or error
- [✓] **Stop/abort button**
  - [✓] Stop button appears only during a download; cancels the running yt-dlp
    process (`terminate()`, then `kill()` after a grace period).
  - [✓] Leaves partial `.part` files on disk and shows the path in the info panel.
  - [✓] Returns to the `info` state so the download can be retried without re-checking.
- [ ] **Cookies from browser (for rate limits / auth)**
  - [ ] Add a UI control to let the user opt in and choose a browser
  - [ ] Pass `--cookies-from-browser <browser>` to yt-dlp when set
  - [ ] Once available, re-add it as a suggestion in the HTTP 429 guidance

---

## P3 — Info panel

Make format lists and progress readable.

- [ ] **Scroll**
  - [ ] Replace single `ttk.Label` with `Text` + `Scrollbar` (or `ScrolledText`)
- [ ] **Copy from info panel**
  - [ ] Allow selecting and copying text (e.g. Ctrl+C, standard context menu)
- [ ] **Wrap text**
  - [ ] Enable word wrap for long lines in the info area
- [ ] **Live status while downloading**
  - [ ] Stream or poll yt-dlp output during download
  - [ ] Show progress/status updates in the info panel
- [ ] **Error styling**
  - [ ] Visually distinguish errors from normal output (e.g. color or tag)

---

## P4 — Media extras

Optional polish after the core flow works.

- [ ] **Thumbnail**
  - [ ] Fetch or extract thumbnail when video info is loaded
  - [ ] Display thumbnail in the UI
- [ ] **Subtitles**
  - [ ] Optional subtitle download (UI toggle + yt-dlp flags)
  - [ ] Document subtitle language/options if applicable

---

## P5 — Multiple downloads

- [ ] **Design**
  - [ ] Decide queue (one at a time) vs limited parallel downloads
  - [ ] Define UI for queue status and per-item progress
- [ ] **Implement**
  - [ ] Queue or manage multiple URLs/downloads
  - [ ] Correct button/state behavior with active queue

---

## P6 — Packaging & quality

Cross-platform release and test coverage (per [Agent guide](AGENTS.md)).

- [ ] **Refactor: separate UI from logic (separation of concerns)**
  - Split the single `main.py` into a **presentation layer** and a
    **domain/logic layer** so the two evolve independently — a classic
    *separation of concerns* / layered (Model–View) design.
  - [ ] Move pure, Tk-free logic (`parse_formats`, `format_id_from_label`,
    `is_rate_limited`, `is_valid_url`, `output_template`/`output_args`,
    `default_output_dir`, and the yt-dlp `subprocess` wrappers) into a
    logic/core module (e.g. `core.py` or a `downloader/` package).
  - [ ] Keep all Tk widget construction and callbacks in a UI module
    (e.g. `ui.py`), depending on the core module — not the reverse.
  - [ ] Reduce the `global current_state`/`_busy` usage by grouping app
    state into a small class or dataclass (per AGENTS.md conventions).
  - [ ] Keep `main.py` as a thin entry point that wires UI + core together.
  - [ ] Update tests to import from the new module(s); no behavior change.
  - Prefer an incremental refactor (extract logic first, then rehome UI) over
    a big-bang rewrite, per AGENTS.md.

- [✓] **Dependencies**
  - [✓] Add `requirements.txt` (or `pyproject.toml` when warranted)
  - [✓] Pin reasonable versions; keep runtime deps minimal
  - _venv moved to P1 (blocks running/testing downloads)._
- [~] **Testing**
  - [✓] Refactor so `main.py` can be imported without launching Tk (guard `Tk()`/`mainloop()` under `if __name__ == "__main__":` or a `main()` function) so logic is unit-testable
  - [✓] Set up pytest under `tests/` (`pytest.ini`, `requirements-dev.txt`)
  - [~] Unit tests: format parsing, format-id extraction, rate-limit detection (`tests/test_formats.py`)
    - [ ] Still to cover: state transitions, URL validation, arg building
  - [ ] Mock subprocess for downloader success/failure/partial output
  - [ ] Integration or smoke tests for UI/threading where practical
- [ ] **PyInstaller**
  - [ ] Add build script or `.spec` for standalone executables
  - [ ] Verify builds on Windows, macOS, and Linux
  - [ ] Decide whether to bundle yt-dlp or document separate install
  - [ ] Do not commit `dist/` or `build/` artifacts

---

## P7 — Polishing & refinements

Optional refinements and follow-ups to features that already work. Not blocking
the core flow; pick these up once higher-priority groups are clear.

- [ ] **Handle video-only/audio-only format picks** _(refines P2 Format selection)_
  - A single video-only or audio-only format id downloads a silent or
    audio-only file.
  - [ ] Auto-combine (e.g. append `+bestaudio` to a video-only pick), or
  - [ ] Warn the user before download when the pick is video-only/audio-only.
- [ ] **Full process-tree termination for Stop** _(follow-up to P2 Stop/abort)_
  - Today Stop signals only yt-dlp's own process. yt-dlp may spawn children
    (ffmpeg for muxing, deno for JS challenges) that can briefly outlive
    `terminate()`.
  - [ ] Kill the whole group/tree with platform-specific setup
    (`start_new_session=True` + `os.killpg` on POSIX;
    `CREATE_NEW_PROCESS_GROUP` / `taskkill /T` on Windows).
- [ ] **Make the format check cancellable** _(follow-up to P2 Stop/abort)_
  - The cancellation machinery in `run_download_live`/`stop_active_proc` is
    written to generalize.
  - [ ] Give `run_download` (the `-F` check) the same register/stop treatment so
    a long-running check can also be aborted.
