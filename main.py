# URL to check:
# https://www.youtube.com/watch?v=dQw4w9WgXcQ

from tkinter import *
from tkinter import ttk
from tkinter import filedialog
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import urllib.parse

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

# Whether a check/download is currently running. The run button is enabled
# only when we're idle AND the URL looks valid; tracking busy separately lets
# both the worker lifecycle and the URL trace recompute that condition.
_busy = False

# --- Cancellation --------------------------------------------------------
# Registry for the currently running, cancellable subprocess so the UI's Stop
# button can terminate it from the main thread while a worker thread streams
# its output. Guarded by a lock because register/stop run on different threads.
# Structured as a small helper set (not hard-wired to "download") so cancelling
# the format check can be added later with the same machinery (see TASKS.md).
_proc_lock = threading.Lock()
_active_proc = None      # the live subprocess.Popen, or None when idle
_cancelled = False       # True when the active process was stopped by the user

# Seconds to wait after terminate() before escalating to kill().
_STOP_GRACE_SECONDS = 3


def _register_proc(proc):
    """Record the running cancellable process (called from a worker thread)."""
    global _active_proc, _cancelled
    with _proc_lock:
        _active_proc = proc
        _cancelled = False


def _clear_proc():
    """Forget the running process once it has finished (worker thread)."""
    global _active_proc
    with _proc_lock:
        _active_proc = None


def stop_active_proc():
    """Terminate the running process, escalating to kill after a grace period.

    Called from the UI thread when the user clicks Stop. Uses terminate() first
    (graceful: SIGTERM on POSIX, TerminateProcess on Windows) and, if the
    process is still alive after _STOP_GRACE_SECONDS, kill()s it.

    Limitation: this signals only yt-dlp's own process, not a full process
    tree. yt-dlp may spawn children (ffmpeg for muxing, deno for JS); those can
    briefly outlive the stop. Killing the whole group/tree needs
    platform-specific setup (start_new_session / CREATE_NEW_PROCESS_GROUP) and
    is tracked as a follow-up in TASKS.md.

    Returns True if a process was signalled, False if none was running.
    """
    global _cancelled
    with _proc_lock:
        proc = _active_proc
        if proc is None:
            return False
        _cancelled = True
    log.info("stop_active_proc: terminating pid=%s", proc.pid)
    proc.terminate()
    try:
        proc.wait(timeout=_STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        log.warning("stop_active_proc: grace expired, killing pid=%s", proc.pid)
        proc.kill()
    return True


def was_cancelled():
    """True if the most recent process was stopped by the user."""
    with _proc_lock:
        return _cancelled


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


# Label used for the default (no explicit -f) entry in the format picker.
DEFAULT_FORMAT_LABEL = "best (default)"


def parse_formats(output):
    """Parse `yt-dlp -F` output into a list of (format_id, label) tuples.

    yt-dlp's `-F` output has a header/separator block followed by one row per
    format, each starting with the format id token. We skip everything up to
    the dashed separator line, then take the first whitespace-delimited token
    on each remaining non-empty line as the id and keep the rest as a
    human-readable label. Ids can be non-numeric (e.g. "sb0", "233"), so we
    don't assume digits — we just require a plausible first token followed by
    more columns.
    """
    if not output:
        return []

    lines = output.splitlines()
    formats = []
    seen_separator = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # The separator is a run of dashes (possibly with spaces/box chars).
        if not seen_separator:
            if set(stripped) <= set("-\u2500 "):
                seen_separator = True
            continue
        parts = stripped.split(None, 1)
        if len(parts) < 2:
            continue
        fmt_id, rest = parts[0], parts[1]
        # Skip stray header-ish lines that slipped past (no real id column).
        if fmt_id.upper() == "ID":
            continue
        label = f"{fmt_id}  {rest}".rstrip()
        formats.append((fmt_id, label))
    return formats


def format_id_from_label(label):
    """Return the format id for a picker label, or None for the default entry.

    Pure helper (no Tk) so it can be unit-tested directly. The id is the first
    whitespace-delimited token of the label produced by `parse_formats`.
    """
    if not label or label == DEFAULT_FORMAT_LABEL:
        return None
    return label.split(None, 1)[0]


def selected_format_id():
    """Return the chosen format id, or None for the default (best) entry."""
    return format_id_from_label(format_var.get())


def default_output_dir():
    """Return a sensible default download directory.

    Prefer the user's Downloads folder when it exists (the conventional place
    for downloads), otherwise fall back to the current working directory. Pure
    (no Tk) so it can be unit-tested.
    """
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.isdir(downloads):
        return downloads
    return os.getcwd()


def output_template(out_dir):
    """Build the yt-dlp `-o` output template for a target directory.

    yt-dlp expects a filename template; join the chosen directory with the
    default `%(title)s [%(id)s].%(ext)s` pattern so files land in that folder
    with readable names. Returns None when no directory is given (let yt-dlp
    use its own default). Pure (no Tk) so it can be unit-tested.
    """
    if not out_dir:
        return None
    return os.path.join(out_dir, "%(title)s [%(id)s].%(ext)s")


def output_args(out_dir):
    """Return yt-dlp args (['-o', template]) for a directory, or [] if none."""
    template = output_template(out_dir)
    return ["-o", template] if template else []


def is_valid_url(url):
    """Return True if the text looks like a usable http(s) URL.

    Deliberately permissive: we only gate the download button on obvious
    non-URLs (empty text, missing scheme, no host) rather than trying to
    validate that a page exists — yt-dlp itself reports unsupported/unreachable
    URLs after a check. Pure (no Tk) so it can be unit-tested.
    """
    if not url:
        return False
    parsed = urllib.parse.urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def parse_download_target(line):
    """Return the destination path from a yt-dlp progress line, or None.

    yt-dlp announces the output file with lines like:
        [download] Destination: /path/Video [id].mp4
        [download] /path/Video [id].mp4 has already been downloaded
    We surface this so that, when a download is stopped, the UI can point the
    user at the (partial) file left on disk. Pure (no Tk) so it's unit-testable.
    """
    if not line:
        return None
    text = line.strip()
    marker = "[download] Destination: "
    if text.startswith(marker):
        return text[len(marker):].strip() or None
    return None


def partial_file_note(target):
    """Build the 'partial file left on disk' note for a stopped download.

    yt-dlp writes to a `.part` file while downloading and renames it on
    completion, so after a stop the leftover is typically `<target>.part`
    (falling back to the target path itself). Returns None when we never saw a
    destination. Pure (no Tk) so it's unit-testable.
    """
    if not target:
        return None
    part = target + ".part"
    which = part if os.path.exists(part) else target
    return f"Partial file left on disk:\n  {which}"


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

    Registers the process so the UI's Stop button can terminate it, and clears
    the registration when it exits. Returns (returncode, stderr) or None if
    yt-dlp not found.
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

    _register_proc(proc)
    try:
        # Stream stdout line by line
        for line in proc.stdout:
            if on_line:
                on_line(line)

        proc.wait()
        stderr = proc.stderr.read()
        proc.stderr.close()
        proc.stdout.close()
    finally:
        _clear_proc()
    log.info("run_download_live: finished rc=%s (stderr %d chars)",
             proc.returncode, len(stderr or ""))
    return proc.returncode, stderr


def set_busy(busy):
    """Disable/enable inputs during background work and refresh button state."""
    global _busy
    _busy = busy
    state = 'disabled' if busy else 'normal'
    url_entry.configure(state=state)
    browse_btn.configure(state=state)
    # The run button and format picker are gated together in one place.
    update_run_btn_state()


def update_run_btn_state(*_args):
    """Sync the run button and format picker to the current input state.

    Bound to the URL variable (so it recomputes as the user types) and called
    from set_busy (so it reflects check/download progress). The action is only
    valid when idle AND the URL looks valid, so gate both controls on that:

    - run button: 'normal' when actionable, else 'disabled'.
    - format picker: 'readonly' (pick-only, not typeable) when actionable,
      else 'disabled' — e.g. it must not stay usable if the user clears the
      URL after a check. Never 'normal', which would let the user type into it.
    """
    ok = (not _busy) and is_valid_url(url_var.get())
    run_btn.configure(state='normal' if ok else 'disabled')
    format_combo.configure(state='readonly' if ok else 'disabled')


def choose_output_dir():
    """Open a folder picker and update the selected download directory."""
    chosen = filedialog.askdirectory(
        title="Choose download folder",
        initialdir=output_dir_var.get() or default_output_dir(),
    )
    if chosen:
        output_dir_var.set(chosen)
        log.info("choose_output_dir: set to %r", chosen)


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
        populate_formats(ret.stdout)
        run_btn_var.set("download")
    set_busy(False)


def populate_formats(output):
    """Fill the format picker from `-F` output and show it."""
    formats = parse_formats(output)
    labels = [DEFAULT_FORMAT_LABEL] + [label for _id, label in formats]
    format_combo.configure(values=labels)
    format_var.set(DEFAULT_FORMAT_LABEL)
    log.info("populate_formats: %d formats parsed", len(formats))
    # Reveal the picker row now that we have formats to choose from.
    format_label.grid()
    format_combo.grid()


def hide_formats():
    """Reset and hide the format picker (used when returning to init)."""
    format_var.set(DEFAULT_FORMAT_LABEL)
    format_combo.configure(values=[DEFAULT_FORMAT_LABEL])
    format_label.grid_remove()
    format_combo.grid_remove()


def show_stop():
    """Reveal the Stop button (only visible while a download runs)."""
    stop_btn.configure(state='normal')
    stop_btn.grid()


def hide_stop():
    """Hide the Stop button when no download is running."""
    stop_btn.grid_remove()


def stop_btn_press(*_args):
    """Stop the running download at the user's request."""
    log.info("stop_btn_press: state=%s", current_state)
    # Disable immediately so a second click can't race the termination.
    stop_btn.configure(state='disabled')
    info_var.set("Stopping...")
    # stop_active_proc() may block up to the grace period waiting for exit, so
    # run it off the UI thread. The download worker will post the final result
    # (via on_download_complete with cancelled=True) once the process ends.
    threading.Thread(target=stop_active_proc, daemon=True, name="stop").start()


def on_download_complete(returncode, stderr, cancelled=False, target=None):
    """Called on main thread when download finishes (or is stopped)."""
    global current_state
    if cancelled:
        # User stopped it: return to 'info' (5b) so formats stay selected and
        # the download can be retried without re-checking. Leave partial files
        # on disk and point the user at them.
        msg = "Download stopped."
        note = partial_file_note(target)
        info_var.set(msg + ("\n\n" + note if note else ""))
        current_state = 'info'
        run_btn_var.set("download")
        hide_stop()
        set_busy(False)
        return
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
    hide_formats()
    hide_stop()
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


def run_download_in_thread(url, fmt_id=None, out_dir=None):
    """Run download in background with live output; post result to main thread."""
    def worker():
        log.info("download worker: started for url=%r fmt=%r out_dir=%r", url, fmt_id, out_dir)
        # Track the latest download destination seen in output so a stop can
        # tell the user which (partial) file was left behind.
        target = {"path": None}

        def on_line(line):
            dest = parse_download_target(line)
            if dest:
                target["path"] = dest
            # Queue UI update on main thread with latest line
            _post(lambda l=line: info_var.set(l.rstrip('\n')))

        # Pass an explicit format id when the user picked one; otherwise let
        # yt-dlp use its default (best) selection. Add an `-o` template when a
        # target directory is set so files land in the chosen folder.
        args = (["-f", fmt_id] if fmt_id else []) + output_args(out_dir) + [url]
        try:
            result = run_download_live(*args, on_line=on_line)
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
            cancelled = was_cancelled()
            log.info("download worker: scheduling on_download_complete rc=%s cancelled=%s",
                     returncode, cancelled)
            _post(lambda: on_download_complete(
                returncode, stderr, cancelled=cancelled, target=target["path"]))

    thread = threading.Thread(target=worker, daemon=True, name="download")
    thread.start()


def run_btn_press(*args):
    global current_state
    log.info("run_btn_press: state=%s url=%r", current_state, url_var.get())
    # Guard the action itself: the <Return> key binding fires even when the
    # button is disabled, so re-check validity/busy here.
    if _busy or not is_valid_url(url_var.get()):
        log.info("run_btn_press: ignored (busy=%s, url valid=%s)",
                 _busy, is_valid_url(url_var.get()))
        return
    if current_state == 'init':
        info_var.set('Getting info...')
        current_state = 'info'
        set_busy(True)
        run_check_in_thread(url_var.get())
    elif current_state == 'info':
        info_var.set('Downloading...')
        set_busy(True)
        show_stop()
        run_download_in_thread(url_var.get(), selected_format_id(), output_dir_var.get())


def _sync_info_text(*_args):
    """Mirror info_var's value into the read-only info Text widget.

    The info panel is a Text (not a Label) so long format lists and output
    scroll. To keep every existing `info_var.set(...)` call site working
    unchanged, info_var stays the source of truth and this trace pushes its
    value into the widget: enable editing, replace all content, disable again
    so the user can't type but can still select/scroll. Autoscroll to the end
    so live download progress stays visible.
    """
    info_text.configure(state='normal')
    info_text.delete('1.0', END)
    info_text.insert('1.0', info_var.get())
    info_text.configure(state='disabled')
    info_text.see(END)


def build_ui(root):
    """Construct all widgets and lay them out on the given Tk root.

    Split out from main() (which owns the event loop) so tests can build the
    real UI on a headless root and assert widget behavior — e.g. that set_busy
    disables the format picker — without duplicating widget construction or
    calling mainloop().
    """
    global frame, url_label, url_var, url_entry
    global run_btn_var, run_btn, stop_btn, format_label, format_var, format_combo
    global output_dir_label, output_dir_var, output_dir_value, browse_btn
    global info_frame, info_var, info_text, info_scroll

    root.title("Video Downloader")

    # |-------------------------------------------------|
    # | frame                                           |
    # |-------------------------------------------------|
    # | url_label    | url_entry        | run_btn | stop_btn |
    # |-------------------------------------------------|
    # | format_label | format_combo               |
    # |-------------------------------------------------|
    # | "Folder:"    | output_dir_value | browse_btn |
    # |-------------------------------------------------|
    # | info_frame + info_label                         |
    # |-------------------------------------------------|

    frame = ttk.Frame(root, padding="3 3 12 12")
    url_label = ttk.Label(frame, text="URL:")
    url_var = StringVar()
    url_entry = ttk.Entry(frame, width=7, textvariable=url_var)
    run_btn_var = StringVar(value="check")
    run_btn = ttk.Button(frame, textvariable=run_btn_var, command=run_btn_press)
    # Stop appears only while a download runs (see show_stop/hide_stop).
    stop_btn = ttk.Button(frame, text="Stop", command=stop_btn_press)
    # Recompute the run button's enabled state as the URL text changes.
    url_var.trace_add("write", update_run_btn_state)
    format_label = ttk.Label(frame, text="Format:")
    format_var = StringVar(value=DEFAULT_FORMAT_LABEL)
    format_combo = ttk.Combobox(
        frame, textvariable=format_var, state="readonly",
        values=[DEFAULT_FORMAT_LABEL],
    )
    output_dir_label = ttk.Label(frame, text="Folder:")
    output_dir_var = StringVar(value=default_output_dir())
    # Show the currently selected folder; readonly entry so long paths scroll
    # and can be copied but not hand-edited (use Browse to change it).
    output_dir_value = ttk.Entry(
        frame, textvariable=output_dir_var, state="readonly",
    )
    browse_btn = ttk.Button(frame, text="Browse...", command=choose_output_dir)
    info_frame = ttk.Frame(frame, borderwidth=1, relief='solid')
    info_var = StringVar()
    # Long format lists and live output need scrolling, so the info panel is a
    # Text widget (not a Label) with a vertical Scrollbar. It's kept read-only
    # (state='disabled') and synced from info_var via a trace (_sync_info_text)
    # so all existing info_var.set(...) call sites keep working unchanged.
    info_text = Text(info_frame, width=40, height=10, wrap='none',
                     state='disabled', borderwidth=0)
    info_scroll = ttk.Scrollbar(info_frame, orient=VERTICAL,
                                command=info_text.yview)
    info_text.configure(yscrollcommand=info_scroll.set)
    info_var.trace_add("write", _sync_info_text)

    frame.grid(column=0, row=0, sticky=(N, W, E, S))
    url_label.grid(column=1, row=1, sticky=E)
    url_entry.grid(column=2, row=1, sticky=(W, E))
    run_btn.grid(column=3, row=1, sticky=W)
    stop_btn.grid(column=4, row=1, sticky=W)
    format_label.grid(column=1, row=2, sticky=E)
    format_combo.grid(column=2, row=2, columnspan=3, sticky=(W, E))
    output_dir_label.grid(column=1, row=3, sticky=E)
    output_dir_value.grid(column=2, row=3, sticky=(W, E))
    browse_btn.grid(column=3, row=3, columnspan=2, sticky=W)
    info_frame.grid(column=1, row=4, columnspan=4, sticky=(N, W, E, S))
    info_text.grid(column=0, row=0, sticky=(N, W, E, S))
    info_scroll.grid(column=1, row=0, sticky=(N, S))

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(2, weight=2)
    frame.rowconfigure(4, weight=2)
    info_frame.columnconfigure(0, weight=1)
    info_frame.rowconfigure(0, weight=1)

    # Apply uniform padding BEFORE hiding widgets below: grid_configure() on a
    # grid_remove()d widget re-maps it, so padding must be set while everything
    # is still gridded, then the initially-hidden widgets removed afterwards.
    for child in frame.winfo_children():
        child.grid_configure(padx=5, pady=5)

    # The format picker starts hidden; it appears after a successful check.
    format_label.grid_remove()
    format_combo.grid_remove()
    # The Stop button starts hidden; it appears only during a download.
    stop_btn.grid_remove()

    # URL starts empty, so the run button starts disabled.
    update_run_btn_state()


def main():
    """Build the Tk UI and run the event loop.

    Widgets are created in build_ui() (not at import time) and published as
    globals so the module can be imported for unit testing without launching
    Tk. The handler functions above reference these names as globals.
    """
    global root

    root = Tk()
    build_ui(root)


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


if __name__ == "__main__":
    main()
