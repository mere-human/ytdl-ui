"""Drive the real ytdl-ui Tk app in-process and screenshot it.

Usage (from repo root, venv python):
    python .claude/skills/run-ytdl-ui/driver.py OUT.png [URL] [--timeout SECS]

Builds the real UI, optionally types URL and presses Check (real yt-dlp,
needs network), waits until the app is idle, grabs the window to OUT.png.
Prints phase / info text / format list so output can be asserted on.
"""
import os
import sys
import time

sys.path.insert(0, os.getcwd())

import ui  # noqa: E402
import core  # noqa: E402
from PIL import ImageGrab  # noqa: E402
from tkinter import Tk  # noqa: E402


def pump(root, secs):
    end = time.time() + secs
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def main():
    args = sys.argv[1:]
    timeout = 90
    if "--timeout" in args:
        i = args.index("--timeout")
        timeout = int(args[i + 1])
        del args[i:i + 2]
    out = args[0] if args else "ytdl-ui.png"
    url = args[1] if len(args) > 1 else None

    core.configure_logging()
    ui.root = root = Tk()
    ui.build_ui(root)
    root.after(50, ui._pump_ui_queue)
    root.geometry("+50+50")
    root.lift()
    root.attributes("-topmost", True)
    pump(root, 0.5)

    if url:
        ui.url_var.set(url)
        pump(root, 0.2)
        ui.run_btn_press()
        deadline = time.time() + timeout
        while ui.state.busy and time.time() < deadline:
            pump(root, 0.1)
        pump(root, 0.5)  # let thumbnail/format list render

    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(out)
    print("phase:", ui.state.phase, "busy:", ui.state.busy)
    print("formats:", list(ui.format_combo["values"])[:5])
    print("info:", ui.info_var.get()[:300].replace("\n", " | "))
    print("screenshot:", os.path.abspath(out))
    root.destroy()


main()
