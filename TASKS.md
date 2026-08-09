# Task list

Prioritized backlog for **ytdl-ui**. Agents: pick the next open item (or a coherent subset) from the highest priority group that has unfinished work. Mark items `[x]` when done.

See also: [Agent guide](AGENTS.md) · [README](README.md)

---

## P1 — Foundation

Core backend and UI responsiveness. Unblocks everything else.

- [x] **Migrate to yt-dlp**
  - [x] Replace all `youtube-dl` CLI invocations with `yt-dlp`
  - [x] Update README and user-facing strings
  - [x] Document yt-dlp install requirement (on PATH for dev)
- [x] **Real download flow**
  - [x] Remove `--help` placeholder; download with selected URL (and format when available)
  - [x] Decode subprocess stdout/stderr as UTF-8 text before showing in UI
  - [x] Reset app state to `init` on failure; surface stderr to the user
- [x] **Graceful error when yt-dlp is missing**
  - [x] Catch `FileNotFoundError` and show actionable message in the info panel
  - [x] Add `requirements.txt` with yt-dlp dependency
- [x] **Non-blocking UI**
  - [x] Run check and download off the main thread (`threading` or `Popen` + polling)
  - [x] Update UI only via `root.after(...)` from worker threads
  - [x] Keep window responsive during long operations
  - [x] Stream live status output during download (`Popen` line-by-line)
  - [x] Update UI with the status output live
- [ ] **Bug: HTTP 429 on URL check**
  - [ ] Reproduce: paste a YouTube URL and check — `Unable to download webpage: HTTP Error 429: Too Many Requests`
  - [ ] Investigate yt-dlp mitigations (update yt-dlp, cookies from browser, retries/sleep, user-agent)
  - [ ] Surface clear, actionable guidance in the UI when rate-limited
- [ ] **Bug: UI is not focused after start**

---

## P2 — Core download workflow

Minimum viable “check → pick → download” experience.

- [ ] **Format selection**
  - [ ] Parse `yt-dlp -F` output into a selectable list
  - [ ] Let user pick a format before download
  - [ ] Pass chosen format id to the download command
- [ ] **Output folder**
  - [ ] Add browse control for download directory
  - [ ] Pass output path to yt-dlp (`-o` or equivalent)
  - [ ] Sensible default (e.g. current directory or user Downloads)
- [ ] **Download button state**
  - [ ] Disable when URL is empty or invalid
  - [ ] Disable while check or download is in progress
  - [ ] Re-enable appropriately on success or error
- [ ] **Stop/abort button**

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

- [x] **Dependencies**
  - [x] Add `requirements.txt` (or `pyproject.toml` when warranted)
  - [x] Pin reasonable versions; keep runtime deps minimal
  - [ ] Use venv
- [ ] **Testing**
  - [ ] Set up pytest under `tests/`
  - [ ] Unit tests: format parsing, state transitions, URL validation, arg building
  - [ ] Mock subprocess for downloader success/failure/partial output
  - [ ] Integration or smoke tests for UI/threading where practical
- [ ] **PyInstaller**
  - [ ] Add build script or `.spec` for standalone executables
  - [ ] Verify builds on Windows, macOS, and Linux
  - [ ] Decide whether to bundle yt-dlp or document separate install
  - [ ] Do not commit `dist/` or `build/` artifacts
