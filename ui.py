# URL to check:
# https://www.youtube.com/watch?v=dQw4w9WgXcQ

from dataclasses import dataclass
from tkinter import E, END, N, S, VERTICAL, W, BooleanVar, StringVar, Text, Tk
from tkinter import ttk
from tkinter import filedialog
import queue
import threading

import core
from core import (
    DEFAULT_FORMAT_LABEL,
    RATE_LIMITED_MSG,
    THUMB_PRINT_TEMPLATE,
    YT_DLP_NOT_FOUND,
    decode_thumbnail,
    default_output_dir,
    fetch_thumbnail_bytes,
    format_id_from_label,
    is_rate_limited,
    is_valid_url,
    log,
    output_args,
    parse_download_target,
    parse_formats,
    parse_thumbnail_url,
    partial_file_note,
    run_download,
    run_download_live,
)


@dataclass
class AppState:
    phase: str = "init"
    busy: bool = False


state = AppState()


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


def selected_format_id():
    """Return the chosen format id, or None for the default (best) entry."""
    return format_id_from_label(format_var.get())


def set_busy(busy):
    """Disable/enable inputs during background work and refresh button state."""
    state.busy = busy
    widget_state = 'disabled' if busy else 'normal'
    url_entry.configure(state=widget_state)
    browse_btn.configure(state=widget_state)
    update_cookie_controls()
    # The run button and format picker are gated together in one place.
    update_run_btn_state()


def selected_cookie_browser():
    """Return the yt-dlp browser id selected in the cookie controls."""
    return core.COOKIE_BROWSERS.get(cookie_browser_var.get())


def update_cookie_controls():
    """Disable cookie settings during work and the browser when opted out."""
    cookie_browser_check.configure(state='disabled' if state.busy else 'normal')
    cookie_browser_combo.configure(
        state='readonly'
        if use_browser_cookies_var.get() and not state.busy
        else 'disabled'
    )


def on_cookie_settings_changed(*_args):
    """Persist the selected browser and whether cookie access is enabled."""
    browser = selected_cookie_browser() or "chrome"
    core.save_cookie_settings(use_browser_cookies_var.get(), browser)
    update_cookie_controls()


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
    ok = (not state.busy) and is_valid_url(url_var.get())
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


def on_check_complete(ret, thumb_bytes=None):
    """Called on main thread when check finishes."""
    log.info("on_check_complete: ret=%s", "None" if ret is None else f"rc={ret.returncode}")
    if ret is None:
        info_var.set(YT_DLP_NOT_FOUND)
        state.phase = 'init'
        hide_thumbnail()
    elif ret.returncode != 0:
        if is_rate_limited(ret.stderr):
            info_var.set(RATE_LIMITED_MSG)
        else:
            info_var.set(ret.stderr if ret.stderr else f'Unknown error: {ret.returncode}')
        state.phase = 'init'
        hide_thumbnail()
    else:
        log.info("on_check_complete: setting info label with %d chars of formats", len(ret.stdout or ""))
        info_var.set(ret.stdout)
        populate_formats(ret.stdout)
        show_thumbnail(thumb_bytes)
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


def show_thumbnail(data):
    """Decode image bytes and show the preview; hide it if decoding fails."""
    global _thumb_photo
    img = decode_thumbnail(data)
    if img is None:
        hide_thumbnail()
        return
    try:
        from PIL import ImageTk
        photo = ImageTk.PhotoImage(img)
    except Exception as exc:
        log.warning("show_thumbnail: %s", exc)
        hide_thumbnail()
        return
    _thumb_photo = photo  # prevent Tk from collecting the image
    thumb_label.configure(image=photo)
    thumb_label.grid()


def hide_thumbnail():
    """Clear and hide the thumbnail preview."""
    global _thumb_photo
    thumb_label.configure(image="")
    thumb_label.grid_remove()
    _thumb_photo = None


def show_stop():
    """Reveal the Stop button (only visible while a download runs)."""
    stop_btn.configure(state='normal')
    stop_btn.grid()


def hide_stop():
    """Hide the Stop button when no download is running."""
    stop_btn.grid_remove()


def stop_btn_press(*_args):
    """Stop the running download at the user's request."""
    log.info("stop_btn_press: state=%s", state.phase)
    # Disable immediately so a second click can't race the termination.
    stop_btn.configure(state='disabled')
    info_var.set("Stopping...")
    # Stopping may block up to the grace period waiting for exit, so
    # run it off the UI thread. The download worker will post the final result
    # (via on_download_complete with cancelled=True) once the process ends.
    def stop_worker():
        try:
            core.process_controller.stop()
        except Exception:
            log.exception("stop worker: unexpected error")

    threading.Thread(target=stop_worker, daemon=True, name="stop").start()


def on_download_complete(returncode, stderr, cancelled=False, target=None):
    """Called on main thread when download finishes (or is stopped)."""
    if cancelled:
        # User stopped it: return to 'info' (5b) so formats stay selected and
        # the download can be retried without re-checking. Leave partial files
        # on disk and point the user at them.
        msg = "Download stopped."
        note = partial_file_note(target)
        info_var.set(msg + ("\n\n" + note if note else ""))
        state.phase = 'info'
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
    state.phase = 'init'
    run_btn_var.set("check")
    hide_formats()
    hide_thumbnail()
    hide_stop()
    set_busy(False)


def run_check_in_thread(url, cookie_browser=None):
    """Run format check in background; post result to main thread."""
    def worker():
        log.info("check worker: started for url=%r", url)
        try:
            ret = run_download(
                "--print", THUMB_PRINT_TEMPLATE, "-F", url,
                cookie_browser=cookie_browser,
            )
        except Exception:
            # Without this, an exception silently kills the thread and the UI
            # stays stuck on "Getting info..." with no clue why.
            log.exception("check worker: unexpected error")
            _post(lambda: (info_var.set(f"Unexpected error — see {core.LOG_PATH}"),
                           set_busy(False)))
            return
        thumb_bytes = None
        if ret is not None and ret.returncode == 0:
            thumb_url = parse_thumbnail_url(ret.stdout)
            if thumb_url:
                log.info("check worker: fetching thumbnail %s", thumb_url)
                thumb_bytes = fetch_thumbnail_bytes(thumb_url)
        log.info("check worker: scheduling on_check_complete on UI thread")
        _post(lambda r=ret, b=thumb_bytes: on_check_complete(r, b))
    thread = threading.Thread(target=worker, daemon=True, name="check")
    thread.start()


def run_download_in_thread(url, fmt_id=None, out_dir=None, cookie_browser=None):
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
            result = run_download_live(
                *args, on_line=on_line, cookie_browser=cookie_browser,
            )
        except Exception:
            log.exception("download worker: unexpected error")
            _post(lambda: (info_var.set(f"Unexpected error — see {core.LOG_PATH}"),
                           set_busy(False)))
            return
        if result is None:
            _post(lambda: (
                info_var.set(YT_DLP_NOT_FOUND),
                set_busy(False),
            ))
        else:
            returncode, stderr = result
            cancelled = core.process_controller.was_cancelled()
            log.info("download worker: scheduling on_download_complete rc=%s cancelled=%s",
                     returncode, cancelled)
            _post(lambda: on_download_complete(
                returncode, stderr, cancelled=cancelled, target=target["path"]))

    thread = threading.Thread(target=worker, daemon=True, name="download")
    thread.start()


def run_btn_press(*args):
    log.info("run_btn_press: state=%s url=%r", state.phase, url_var.get())
    # Guard the action itself: the <Return> key binding fires even when the
    # button is disabled, so re-check validity/busy here.
    if state.busy or not is_valid_url(url_var.get()):
        log.info("run_btn_press: ignored (busy=%s, url valid=%s)",
                 state.busy, is_valid_url(url_var.get()))
        return
    if state.phase == 'init':
        info_var.set('Getting info...')
        state.phase = 'info'
        hide_thumbnail()
        set_busy(True)
        cookie_browser = (
            selected_cookie_browser() if use_browser_cookies_var.get() else None
        )
        run_check_in_thread(url_var.get(), cookie_browser)
    elif state.phase == 'info':
        info_var.set('Downloading...')
        set_busy(True)
        show_stop()
        cookie_browser = (
            selected_cookie_browser() if use_browser_cookies_var.get() else None
        )
        run_download_in_thread(
            url_var.get(), selected_format_id(), output_dir_var.get(), cookie_browser,
        )


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
    global cookie_options_frame, use_browser_cookies_var, cookie_browser_var
    global cookie_browser_check, cookie_browser_combo
    global content_frame, thumb_label, info_frame, info_var, info_text, info_scroll

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
    # | cookie options                               |
    # |-------------------------------------------------|
    # | content_frame: thumb_label | info_frame         |
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
    cookies_enabled, cookie_browser = core.load_cookie_settings()
    use_browser_cookies_var = BooleanVar(value=cookies_enabled)
    cookie_browser_var = StringVar(
        value=next(
            (label for label, value in core.COOKIE_BROWSERS.items()
             if value == cookie_browser),
            "Chrome",
        )
    )
    cookie_options_frame = ttk.Frame(frame)
    cookie_browser_check = ttk.Checkbutton(
        cookie_options_frame,
        text="Use browser cookies",
        variable=use_browser_cookies_var,
        command=on_cookie_settings_changed,
    )
    cookie_browser_combo = ttk.Combobox(
        cookie_options_frame,
        textvariable=cookie_browser_var,
        state="readonly",
        values=list(core.COOKIE_BROWSERS),
        width=12,
    )
    cookie_browser_combo.bind(
        "<<ComboboxSelected>>", on_cookie_settings_changed,
    )
    content_frame = ttk.Frame(frame)
    # Preview appears after a successful check; hidden until then.
    thumb_label = ttk.Label(content_frame)
    info_frame = ttk.Frame(content_frame, borderwidth=1, relief='solid')
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
    cookie_options_frame.grid(column=1, row=4, columnspan=4, sticky=W)
    cookie_browser_check.grid(column=0, row=0, sticky=W)
    ttk.Label(cookie_options_frame, text="Browser:").grid(column=1, row=0, sticky=E)
    cookie_browser_combo.grid(column=2, row=0, sticky=W)
    content_frame.grid(column=1, row=5, columnspan=4, sticky=(N, W, E, S))
    thumb_label.grid(column=0, row=0, sticky=N, padx=(0, 8))
    info_frame.grid(column=1, row=0, sticky=(N, W, E, S))
    info_text.grid(column=0, row=0, sticky=(N, W, E, S))
    info_scroll.grid(column=1, row=0, sticky=(N, S))

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(2, weight=2)
    frame.rowconfigure(5, weight=2)
    content_frame.columnconfigure(1, weight=1)
    content_frame.rowconfigure(0, weight=1)
    info_frame.columnconfigure(0, weight=1)
    info_frame.rowconfigure(0, weight=1)

    # Apply uniform padding BEFORE hiding widgets below: grid_configure() on a
    # grid_remove()d widget re-maps it, so padding must be set while everything
    # is still gridded, then the initially-hidden widgets removed afterwards.
    for child in frame.winfo_children():
        child.grid(padx=5, pady=5)

    # The format picker starts hidden; it appears after a successful check.
    format_label.grid_remove()
    format_combo.grid_remove()
    # Thumbnail starts hidden; it appears after a successful check.
    thumb_label.grid_remove()
    # The Stop button starts hidden; it appears only during a download.
    stop_btn.grid_remove()

    update_cookie_controls()
    # URL starts empty, so the run button starts disabled.
    update_run_btn_state()


def main():
    """Build the Tk UI and run the event loop.

    Widgets are created in build_ui() (not at import time) and published as
    globals so the module can be imported for unit testing without launching
    Tk. The handler functions above reference these names as globals.
    """
    global root

    try:
        core.configure_logging()
        root = Tk()
        build_ui(root)
    except Exception:
        log.exception("Application startup failed")
        raise

    def report_callback_exception(exc, value, traceback):
        log.error("Unhandled Tk callback exception", exc_info=(exc, value, traceback))

    root.report_callback_exception = report_callback_exception


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
