---
name: run-ytdl-ui
description: Run, start, launch, drive, screenshot, or test the ytdl-ui Tkinter desktop app (yt-dlp GUI). Use to see a UI change working in the real app, check a URL, or capture a screenshot.
---

ytdl-ui is a Tkinter wrapper around yt-dlp.
Paths below are relative to the repo root.
Verified on Windows 11 with a real desktop session, using the project venv (Python 3.12).
I did not try Linux or macOS.

## Prerequisites

```bash
python -m venv .venv                      # Python 3.11+
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

This installs yt-dlp, deno, Pillow and pytest into the venv.
On macOS/Linux the venv python is `.venv/bin/python`.

## Run (agent path)

`driver.py` builds the real UI in-process, optionally types a URL and presses Check, waits until the app is idle, then saves a PNG of the window.
It prints the phase, the format list and the info text, so the output can be asserted on.

```bash
# idle UI
.venv/Scripts/python .claude/skills/run-ytdl-ui/driver.py "$TEMP/idle.png"
# real check (needs network; takes about 10s)
.venv/Scripts/python .claude/skills/run-ytdl-ui/driver.py "$TEMP/check.png" "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --timeout 120
```

After a check, expect `phase: info busy: False`, around 49 formats, and a thumbnail in the screenshot.
Open the PNG with Read and look at it.

To exercise other widgets, edit `driver.py`: `ui.*` globals such as `url_var`, `format_combo` and `run_btn_press` are all available after `build_ui`.
The loop calls `root.update()` and does not use `mainloop()`.

## Run (human path)

`python main.py` opens the window and blocks until it is closed.

## Test

```bash
.venv/Scripts/python -m pytest -q     # 100 passed, 2 skipped
```

## Gotchas

- The driver uses your real saved settings in `%LOCALAPPDATA%\ytdl-ui\settings.json`.
  If cookies are enabled there, the check passes `--cookies <file>` and the screenshot shows the cookie rows.
  Nothing is written back unless you change the cookie widgets.
- Use `ImageGrab` of the window's bounding box.
  It needs a real, unlocked display.
- The driver does not run a Download.
  Download saves into the Downloads folder and can be large, so call `ui.run_btn_press()` a second time only on purpose.
- Don't use `root.after` from threads.
  The driver pumps `ui._pump_ui_queue` itself, because `main()` is not used.

## Troubleshooting

- `ModuleNotFoundError: ui` means you ran the driver from outside the repo root.
  It inserts `os.getcwd()` on `sys.path`.
- A check that hits the timeout leaves `busy: True`.
  See `%TEMP%\ytdl-ui\ytdl-ui-<pid>.log` for the yt-dlp stderr.
