# URL to check:
# https://www.youtube.com/watch?v=dQw4w9WgXcQ

from tkinter import *
from tkinter import ttk
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading

# --- Logging -------------------------------------------------------------
# Logs go to stderr (visible in the launching terminal) and to ytdl-ui.log
# next to this script, so hangs/errors are diagnosable when run from the UI.
# Quiet by default (WARNING); set YTDL_UI_LOG to a level name (e.g. INFO or
# DEBUG) to see the full check/download flow.
_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ytdl-ui.log")
logging.basicConfig(
    level=os.environ.get("YTDL_UI_LOG", "WARNING").upper(),
    format="%(asctime)s %(levelname)s [%(threadName)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr), logging.FileHandler(_LOG_PATH)],
)
log = logging.getLogger("ytdl-ui")

current_state = 'init'

# --- Thread -> UI bridge -------------------------------------------------
# Cross-thread `root.after(...)` calls are not reliably delivered on macOS Tk
# (the callback can sit un-processed, leaving the UI stuck). Instead, worker
# threads push callables onto this queue and the MAIN thread drains it via a
# self-scheduled `after` loop — main-thread `after` callbacks are always run.
_ui_queue = queue.Queue()


def _post(fn):
    """Queue a zero-arg callable to run on the Tk main thread."""
    _ui_queue.put(fn)


def _pump_ui_queue():
    """Drain queued UI callables on the main thread; reschedule itself."""
    try:
        while True:
            fn = _ui_queue.get_nowait()
            try:
                fn()
            except Exception:
                log.exception("UI callback failed")
    except queue.Empty:
        pass
    root.after(50, _pump_ui_queue)


def _venv_bin_dir():
    """Directory containing the running interpreter (venv's bin/Scripts)."""
    return os.path.dirname(os.path.abspath(sys.executable))


def _find_executable(name):
    """Locate an executable, preferring the venv's bin dir over PATH.

    Keeping the JS runtime (deno) and yt-dlp inside the venv means downloads
    work without any system-wide installs. On Windows the binary may carry an
    .exe suffix, so probe common variants next to the interpreter first.
    """
    bin_dir = _venv_bin_dir()
    for candidate in (name, name + ".exe"):
        local = os.path.join(bin_dir, candidate)
        if os.path.isfile(local) and os.access(local, os.X_OK):
            return local
    return shutil.which(name)


# yt-dlp: prefer the venv copy so we don't depend on a system-wide install.
YT_DLP = _find_executable("yt-dlp") or "yt-dlp"


def _js_runtime_opts():
    """Point yt-dlp at a JavaScript runtime, preferring the venv's deno.

    yt-dlp needs a JS runtime to solve YouTube's signature/n challenges.
    It only auto-enables deno, and only if deno is on PATH. Since we install
    deno into the venv (`pip install deno`), pass its explicit path so the app
    works regardless of how it was launched. If no local deno is found, return
    no options and let yt-dlp fall back to whatever it can auto-detect.
    """
    bin_dir = _venv_bin_dir()
    for candidate in ("deno", "deno.exe"):
        deno = os.path.join(bin_dir, candidate)
        if os.path.isfile(deno) and os.access(deno, os.X_OK):
            return ["--js-runtimes", f"deno:{deno}"]
    return []


JS_RUNTIME_OPTS = _js_runtime_opts()

log.info("Python %s", sys.version.split()[0])
log.info("yt-dlp resolved to: %s", YT_DLP)
log.info("JS runtime opts: %s", JS_RUNTIME_OPTS or "(none — yt-dlp will auto-detect)")

YT_DLP_NOT_FOUND = (
    'Error: yt-dlp not found. Install it with:\n'
    '  pip install -r requirements.txt\n'
    'or visit https://github.com/yt-dlp/yt-dlp#installation'
)

RATE_LIMITED_MSG = (
    'Rate limited by the server (HTTP 429: Too Many Requests).\n'
    '\n'
    'Try the following:\n'
    '  - Wait a few minutes before retrying.\n'
    '  - Update yt-dlp: pip install -U yt-dlp\n'
    '  - Avoid checking many URLs in quick succession.'
)

# Options that reduce the chance of hitting HTTP 429 by retrying with
# exponential backoff and sleeping between requests/retries.
RATE_LIMIT_OPTS = [
    "--retries", "10",
    "--retry-sleep", "exp=1:120",
    "--sleep-requests", "1",
]


def is_rate_limited(text):
    """Return True if the given output looks like an HTTP 429 rate limit."""
    if not text:
        return False
    lowered = text.lower()
    return "429" in text or "too many requests" in lowered


def run_download(*args):
    """Run yt-dlp and return the CompletedProcess, or None if not found."""
    cmd = [YT_DLP, *JS_RUNTIME_OPTS, *RATE_LIMIT_OPTS, *args]
    log.info("run_download: starting: %s", " ".join(cmd))
    try:
        ret = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        log.info(
            "run_download: finished rc=%s (stdout %d chars, stderr %d chars)",
            ret.returncode, len(ret.stdout or ""), len(ret.stderr or ""),
        )
        return ret
    except FileNotFoundError:
        log.error("run_download: yt-dlp not found at %s", YT_DLP)
        return None


def run_download_live(*args, on_line=None):
    """Run yt-dlp with live line-by-line output via on_line callback.

    Returns (returncode, stderr) or None if yt-dlp not found.
    """
    cmd = [YT_DLP, *JS_RUNTIME_OPTS, *RATE_LIMIT_OPTS, *args]
    log.info("run_download_live: starting: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        log.error("run_download_live: yt-dlp not found at %s", YT_DLP)
        return None

    # Stream stdout line by line
    for line in proc.stdout:
        if on_line:
            on_line(line)

    proc.wait()
    stderr = proc.stderr.read()
    proc.stderr.close()
    proc.stdout.close()
    log.info("run_download_live: finished rc=%s (stderr %d chars)",
             proc.returncode, len(stderr or ""))
    return proc.returncode, stderr


def set_busy(busy):
    """Disable/enable the button and entry during background work."""
    state = 'disabled' if busy else 'normal'
    run_btn.configure(state=state)
    url_entry.configure(state=state)


def on_check_complete(ret):
    """Called on main thread when check finishes."""
    global current_state
    log.info("on_check_complete: ret=%s", "None" if ret is None else f"rc={ret.returncode}")
    if ret is None:
        info_var.set(YT_DLP_NOT_FOUND)
        current_state = 'init'
    elif ret.returncode != 0:
        if is_rate_limited(ret.stderr):
            info_var.set(RATE_LIMITED_MSG)
        else:
            info_var.set(ret.stderr if ret.stderr else f'Unknown error: {ret.returncode}')
        current_state = 'init'
    else:
        log.info("on_check_complete: setting info label with %d chars of formats", len(ret.stdout or ""))
        info_var.set(ret.stdout)
        run_btn_var.set("download")
    set_busy(False)


def on_download_complete(returncode, stderr):
    """Called on main thread when download finishes."""
    global current_state
    if returncode != 0:
        if is_rate_limited(stderr):
            info_var.set(RATE_LIMITED_MSG)
        else:
            info_var.set(stderr if stderr else f'Unknown error: {returncode}')
    else:
        # Append completion message to current output
        current = info_var.get()
        if not current or current == 'Downloading...':
            info_var.set('Download complete.')
        else:
            info_var.set(current.rstrip('\n') + '\nDownload complete.')
    current_state = 'init'
    run_btn_var.set("check")
    set_busy(False)


def run_check_in_thread(url):
    """Run format check in background; post result to main thread."""
    def worker():
        log.info("check worker: started for url=%r", url)
        try:
            ret = run_download("-F", url)
        except Exception:
            # Without this, an exception silently kills the thread and the UI
            # stays stuck on "Getting info..." with no clue why.
            log.exception("check worker: unexpected error")
            _post(lambda: (info_var.set("Unexpected error — see ytdl-ui.log"),
                           set_busy(False)))
            return
        log.info("check worker: scheduling on_check_complete on UI thread")
        _post(lambda: on_check_complete(ret))
    thread = threading.Thread(target=worker, daemon=True, name="check")
    thread.start()


def run_download_in_thread(url):
    """Run download in background with live output; post result to main thread."""
    def worker():
        log.info("download worker: started for url=%r", url)
        def on_line(line):
            # Queue UI update on main thread with latest line
            _post(lambda l=line: info_var.set(l.rstrip('\n')))

        try:
            result = run_download_live(url, on_line=on_line)
        except Exception:
            log.exception("download worker: unexpected error")
            _post(lambda: (info_var.set("Unexpected error — see ytdl-ui.log"),
                           set_busy(False)))
            return
        if result is None:
            _post(lambda: (
                info_var.set(YT_DLP_NOT_FOUND),
                set_busy(False),
            ))
        else:
            returncode, stderr = result
            log.info("download worker: scheduling on_download_complete rc=%s", returncode)
            _post(lambda: on_download_complete(returncode, stderr))

    thread = threading.Thread(target=worker, daemon=True, name="download")
    thread.start()


def run_btn_press(*args):
    global current_state
    log.info("run_btn_press: state=%s url=%r", current_state, url_var.get())
    if current_state == 'init':
        info_var.set('Getting info...')
        current_state = 'info'
        set_busy(True)
        run_check_in_thread(url_var.get())
    elif current_state == 'info':
        info_var.set('Downloading...')
        set_busy(True)
        run_download_in_thread(url_var.get())


root = Tk()
root.title("Video Downloader")

# |---------------------------------|
# | frame                           |
# |---------------------------------|
# | url_label | url_entry | run_btn |
# |---------------------------------|
# | info_frame + info_label         |
# |---------------------------------|

frame = ttk.Frame(root, padding="3 3 12 12")
url_label = ttk.Label(frame, text="URL:")
url_var = StringVar()
url_entry = ttk.Entry(frame, width=7, textvariable=url_var)
run_btn_var = StringVar(value="check")
run_btn = ttk.Button(frame, textvariable=run_btn_var, command=run_btn_press)
info_frame = ttk.Frame(frame, borderwidth=1, relief='solid')
info_var = StringVar()
info_label = ttk.Label(info_frame, textvariable=info_var)

frame.grid(column=0, row=0, sticky=(N, W, E, S))
url_label.grid(column=1, row=1, sticky=E)
url_entry.grid(column=2, row=1, sticky=(W, E))
run_btn.grid(column=3, row=1, sticky=W)
info_frame.grid(column=1, row=2, columnspan=3, sticky=(N, W, E, S))
info_label.grid(column=0, row=0, sticky=(N, W, E, S))

root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)
frame.columnconfigure(2, weight=2)
frame.rowconfigure(2, weight=2)
info_frame.columnconfigure(0, weight=1)
info_frame.rowconfigure(0, weight=1)

for child in frame.winfo_children():
    child.grid_configure(padx=5, pady=5)

def focus_window():
    """Bring the app window to the foreground and focus the URL entry.

    Just calling widget.focus() sets focus within the app but does not
    guarantee the OS raises the window to the front on launch (notably on
    macOS/Windows). Temporarily setting topmost + lift() forces it forward.
    """
    root.lift()
    root.attributes('-topmost', True)
    # Drop topmost right after so the window doesn't stay pinned above others.
    root.after(0, lambda: root.attributes('-topmost', False))
    root.focus_force()
    url_entry.focus_set()


root.bind("<Return>", run_btn_press)
root.after(0, focus_window)
# Start draining the thread->UI queue on the main thread.
root.after(50, _pump_ui_queue)

root.mainloop()
