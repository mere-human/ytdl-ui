# URL to check:
# https://www.youtube.com/watch?v=dQw4w9WgXcQ

from dataclasses import dataclass
from tkinter import E, END, N, S, VERTICAL, W, BooleanVar, StringVar, Text, Tk, Toplevel
from tkinter import ttk
from tkinter import filedialog
import queue
import os
import threading

import core
from core import (
    AUTO_SUBS_PRINT_TEMPLATE,
    FORMAT_TYPES,
    RATE_LIMITED_MSG,
    SUBS_PRINT_TEMPLATE,
    THUMB_PRINT_TEMPLATE,
    YT_DLP_NOT_FOUND,
    decode_thumbnail,
    default_output_dir,
    fetch_thumbnail_bytes,
    is_rate_limited,
    is_valid_url,
    log,
    output_args,
    parse_download_target,
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


def selected_format_args():
    """Return the yt-dlp args for the current format/subtitle selection."""
    custom = custom_format_var.get()
    if custom:
        args = core.custom_format_args(custom, format_details)
    else:
        args = core.format_selection_args(
            format_var.get(), quality_var.get(), container_var.get(),
        )
    if subs_var.get() and subtitle_langs:
        args += core.subtitle_args(subs_lang_var.get())
    return args


def update_size_label(*_args):
    """Show the estimated download size for the current selection."""
    if custom_format_var.get():
        info = next((f for f in format_details if f.id == custom_format_var.get()), None)
        size = info.size if info else None
    else:
        size = core.estimate_size(format_details, format_var.get(), quality_var.get())
    size_var.set(core.format_size(size))


def on_format_type_changed(*_args):
    """Refresh quality/container choices after the download type changes."""
    fmt_type = format_var.get()
    quality_combo.configure(values=core.quality_choices(fmt_type, format_details))
    container_combo.configure(values=core.container_choices(fmt_type))
    quality_var.set(core.QUALITY_BEST)
    container_var.set(core.container_choices(fmt_type)[0])
    update_size_label()


def update_custom_format_label():
    """Show or hide the custom-format indicator and refresh dependent controls."""
    custom = custom_format_var.get()
    if custom:
        custom_label.configure(text=f"Custom format: {custom}")
        custom_label.grid()
        custom_clear_btn.grid()
    else:
        custom_label.grid_remove()
        custom_clear_btn.grid_remove()
    update_size_label()
    update_run_btn_state()


def clear_custom_format(*_args):
    """Go back to the preset controls."""
    custom_format_var.set("")
    update_custom_format_label()


def show_all_formats():
    """Open a table of every parsed format and let the user pick one."""
    win = Toplevel(root)
    win.title("All formats")
    win.transient(root)
    columns = ("id", "ext", "resolution", "type", "size", "detail")
    headings = ("ID", "Ext", "Resolution", "Type", "Size", "Details")
    widths = (60, 60, 90, 90, 90, 360)
    tree = ttk.Treeview(win, columns=columns, show="headings", selectmode="browse")
    for col, heading, width in zip(columns, headings, widths):
        tree.heading(col, text=heading)
        tree.column(col, width=width, anchor=W, stretch=(col == "detail"))
    scroll = ttk.Scrollbar(win, orient=VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    type_names = {"video+audio": "video + audio", "video": "video only", "audio": "audio only"}
    for f in core.sort_formats_for_display(format_details):
        size = core.format_size(f.size) if f.size else ""
        tree.insert("", END, iid=f.id, values=(
            f.id, f.ext, f.resolution, type_names[f.kind], size, f.detail))
    if custom_format_var.get() and tree.exists(custom_format_var.get()):
        tree.selection_set(custom_format_var.get())
        tree.see(custom_format_var.get())

    def use_selected(*_a):
        sel = tree.selection()
        if sel:
            custom_format_var.set(sel[0])
            update_custom_format_label()
            win.destroy()

    buttons = ttk.Frame(win)
    ttk.Button(buttons, text="Use selected format", command=use_selected).grid(
        column=0, row=0, padx=5, pady=5)
    ttk.Button(buttons, text="Close", command=win.destroy).grid(
        column=1, row=0, padx=5, pady=5)
    tree.grid(column=0, row=0, sticky=(N, W, E, S))
    scroll.grid(column=1, row=0, sticky=(N, S))
    buttons.grid(column=0, row=1, columnspan=2, sticky=E)
    win.columnconfigure(0, weight=1)
    win.rowconfigure(0, weight=1)
    tree.bind("<Double-1>", use_selected)


def set_busy(busy):
    """Disable/enable inputs during background work and refresh button state."""
    state.busy = busy
    widget_state = 'disabled' if busy else 'normal'
    url_entry.configure(state=widget_state)
    browse_btn.configure(state=widget_state)
    update_cookie_controls()
    # The run button and format controls are gated together in one place.
    update_run_btn_state()


def selected_cookie_browser():
    """Return the yt-dlp browser id selected in the cookie controls."""
    return core.COOKIE_BROWSERS.get(cookie_browser_var.get())


def selected_cookie_file():
    """Return the selected cookie file when file mode is active."""
    if cookie_source_var.get() == "file":
        return cookie_file_var.get() or None
    return None


def update_cookie_file_label():
    """Show the active cookie-file path without making it editable."""
    if cookie_source_var.get() == "file" and cookie_file_var.get():
        cookie_file_label.configure(text=f"Cookie file: {cookie_file_var.get()}")
        cookie_file_label.grid()
    else:
        cookie_file_label.grid_remove()


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
    browser = selected_cookie_browser() or core.COOKIE_BROWSERS.get(
        cookie_previous_browser_var.get(), "chrome",
    )
    core.save_cookie_settings(
        use_browser_cookies_var.get(), browser,
        cookie_file_var.get(), cookie_source_var.get(),
    )
    update_cookie_file_label()
    update_cookie_controls()


def choose_cookie_file():
    """Open a cookie-file picker and activate the chosen file source."""
    current_file = cookie_file_var.get()
    chosen = filedialog.askopenfilename(
        title="Choose cookie file",
        initialdir=os.path.dirname(current_file) if current_file else None,
        filetypes=(("Cookie files", "*.txt"), ("All files", "*.*")),
    )
    if not chosen:
        return False
    cookie_file_var.set(chosen)
    cookie_source_var.set("file")
    cookie_browser_var.set("Browse...")
    on_cookie_settings_changed()
    log.info("choose_cookie_file: selected %r", chosen)
    return True


def on_cookie_browser_selected(*_args):
    """Handle browser choices and the final Browse... combo item."""
    if cookie_browser_var.get() == "Browse...":
        if not choose_cookie_file():
            cookie_browser_var.set(
                "Browse..." if cookie_source_var.get() == "file"
                else cookie_previous_browser_var.get()
            )
        return
    cookie_previous_browser_var.set(cookie_browser_var.get())
    cookie_source_var.set("browser")
    on_cookie_settings_changed()


def update_run_btn_state(*_args):
    """Sync the run button and format picker to the current input state.

    Bound to the URL variable (so it recomputes as the user types) and called
    from set_busy (so it reflects check/download progress). The action is only
    valid when idle AND the URL looks valid, so gate both controls on that:

    - run button: 'normal' when actionable, else 'disabled'.
    - format controls: 'readonly' (pick-only, not typeable) when actionable,
      else 'disabled' — e.g. they must not stay usable if the user clears the
      URL after a check. Never 'normal', which would let the user type into them.
      The preset dropdowns also stay disabled while a custom format is active.
    """
    ok = (not state.busy) and is_valid_url(url_var.get())
    run_btn.configure(state='normal' if ok else 'disabled')
    presets_state = 'readonly' if ok and not custom_format_var.get() else 'disabled'
    for combo in (format_combo, quality_combo, container_combo):
        combo.configure(state=presets_state)
    has_subs = bool(subtitle_langs)
    subs_check.configure(state='normal' if ok and has_subs else 'disabled')
    subs_combo.configure(
        state='readonly' if ok and has_subs and subs_var.get() else 'disabled')
    all_formats_btn.configure(state='normal' if ok else 'disabled')
    custom_clear_btn.configure(state='normal' if ok else 'disabled')


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
        info_var.set(core.strip_print_lines(ret.stdout))
        populate_formats(ret.stdout)
        show_thumbnail(thumb_bytes)
        run_btn_var.set("download")
    set_busy(False)


def populate_formats(output):
    """Fill the format controls from `-F` output and show them."""
    global format_details, subtitle_langs
    format_details = core.parse_format_details(output)
    subtitle_langs = core.parse_subtitle_languages(output)
    custom_format_var.set("")
    format_combo.configure(values=list(FORMAT_TYPES))
    format_var.set(FORMAT_TYPES[0])
    on_format_type_changed()
    subs_var.set(False)
    subs_combo.configure(values=subtitle_langs)
    subs_lang_var.set(subtitle_langs[0] if subtitle_langs else "")
    subs_check.configure(
        text="Subtitles" if subtitle_langs else "Subtitles (none available)")
    update_custom_format_label()
    log.info("populate_formats: %d formats, %d subtitle tracks",
             len(format_details), len(subtitle_langs))
    # Reveal the format rows now that we have formats to choose from.
    format_label.grid()
    format_frame.grid()
    options_frame.grid()


def hide_formats():
    """Reset and hide the format controls (used when returning to init)."""
    global format_details, subtitle_langs
    format_details = []
    subtitle_langs = []
    custom_format_var.set("")
    format_var.set(FORMAT_TYPES[0])
    subs_var.set(False)
    format_label.grid_remove()
    format_frame.grid_remove()
    options_frame.grid_remove()


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


def run_check_in_thread(url, cookie_browser=None, cookie_file=None):
    """Run format check in background; post result to main thread."""
    def worker():
        log.info("check worker: started for url=%r", url)
        try:
            ret = run_download(
                "--print", THUMB_PRINT_TEMPLATE,
                "--print", SUBS_PRINT_TEMPLATE,
                "--print", AUTO_SUBS_PRINT_TEMPLATE,
                "-F", url,
                cookie_browser=cookie_browser,
                cookie_file=cookie_file,
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


def run_download_in_thread(
    url, format_args=None, out_dir=None, cookie_browser=None, cookie_file=None,
):
    """Run download in background with live output; post result to main thread."""
    def worker():
        log.info("download worker: started for url=%r format_args=%r out_dir=%r",
                 url, format_args, out_dir)
        # Track the latest download destination seen in output so a stop can
        # tell the user which (partial) file was left behind.
        target = {"path": None}

        def on_line(line):
            dest = parse_download_target(line)
            if dest:
                target["path"] = dest
            # Queue UI update on main thread with latest line
            _post(lambda l=line: info_var.set(l.rstrip('\n')))

        # Pass the format/subtitle args built from the UI choices. Add an
        # `-o` template when a target directory is set so files land in the
        # chosen folder.
        args = list(format_args or []) + output_args(out_dir) + [url]
        try:
            result = run_download_live(
                *args, on_line=on_line, cookie_browser=cookie_browser,
                cookie_file=cookie_file,
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
        cookie_browser = selected_cookie_browser() if use_browser_cookies_var.get() else None
        cookie_file = selected_cookie_file() if use_browser_cookies_var.get() else None
        run_check_in_thread(url_var.get(), cookie_browser, cookie_file)
    elif state.phase == 'info':
        info_var.set('Downloading...')
        set_busy(True)
        show_stop()
        cookie_browser = selected_cookie_browser() if use_browser_cookies_var.get() else None
        cookie_file = selected_cookie_file() if use_browser_cookies_var.get() else None
        run_download_in_thread(
            url_var.get(), selected_format_args(), output_dir_var.get(),
            cookie_browser, cookie_file,
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
    global format_frame, quality_var, quality_combo, container_var, container_combo
    global size_var, size_label, options_frame, subs_var, subs_check, subs_lang_var
    global subs_combo, all_formats_btn, custom_format_var, custom_label
    global custom_clear_btn, format_details, subtitle_langs
    global output_dir_label, output_dir_var, output_dir_value, browse_btn
    global cookie_options_frame, use_browser_cookies_var, cookie_browser_var
    global cookie_browser_check, cookie_browser_combo, cookie_file_label
    global cookie_file_var, cookie_source_var, cookie_previous_browser_var
    global content_frame, thumb_label, info_frame, info_var, info_text, info_scroll

    root.title("Video Downloader")

    # |-------------------------------------------------|
    # | frame                                           |
    # |-------------------------------------------------|
    # | url_label    | url_entry        | run_btn | stop_btn |
    # |-------------------------------------------------|
    # | format_label | type | quality | container | size |
    # |              | subtitles | lang | all formats      |
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
    format_details = []
    subtitle_langs = []
    format_label = ttk.Label(frame, text="Format:")
    format_frame = ttk.Frame(frame)
    format_var = StringVar(value=FORMAT_TYPES[0])
    format_combo = ttk.Combobox(
        format_frame, textvariable=format_var, state="readonly",
        values=list(FORMAT_TYPES), width=14,
    )
    quality_var = StringVar(value=core.QUALITY_BEST)
    quality_combo = ttk.Combobox(
        format_frame, textvariable=quality_var, state="readonly",
        values=[core.QUALITY_BEST], width=10,
    )
    container_var = StringVar(value=core.VIDEO_CONTAINERS[0])
    container_combo = ttk.Combobox(
        format_frame, textvariable=container_var, state="readonly",
        values=list(core.VIDEO_CONTAINERS), width=10,
    )
    size_var = StringVar()
    size_label = ttk.Label(format_frame, textvariable=size_var)
    format_combo.bind("<<ComboboxSelected>>", on_format_type_changed)
    quality_combo.bind("<<ComboboxSelected>>", update_size_label)
    container_combo.bind("<<ComboboxSelected>>", update_size_label)
    options_frame = ttk.Frame(frame)
    subs_var = BooleanVar(value=False)
    subs_lang_var = StringVar()
    subs_check = ttk.Checkbutton(
        options_frame, text="Subtitles", variable=subs_var,
        command=update_run_btn_state,
    )
    subs_combo = ttk.Combobox(
        options_frame, textvariable=subs_lang_var, state="disabled", width=28,
    )
    all_formats_btn = ttk.Button(
        options_frame, text="Show all formats...", command=show_all_formats,
    )
    custom_format_var = StringVar(value="")
    custom_label = ttk.Label(options_frame, text="")
    custom_clear_btn = ttk.Button(
        options_frame, text="Clear", command=clear_custom_format, width=6,
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
    cookie_file, cookie_source = core.load_cookie_file_settings()
    use_browser_cookies_var = BooleanVar(value=cookies_enabled)
    browser_label = next(
        (label for label, value in core.COOKIE_BROWSERS.items()
         if value == cookie_browser),
        "Chrome",
    )
    if cookie_source != "file" or not cookie_file:
        cookie_source = "browser"
    cookie_browser_var = StringVar(
        value="Browse..." if cookie_source == "file" else browser_label
    )
    cookie_previous_browser_var = StringVar(value=browser_label)
    cookie_file_var = StringVar(value=cookie_file)
    cookie_source_var = StringVar(value=cookie_source)
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
        values=[*core.COOKIE_BROWSERS, "Browse..."],
        width=12,
    )
    cookie_browser_combo.bind(
        "<<ComboboxSelected>>", on_cookie_browser_selected,
    )
    cookie_file_label = ttk.Label(cookie_options_frame, text="", wraplength=500)
    content_frame = ttk.Frame(frame)
    # Preview appears after a successful check; hidden until then.
    thumb_label = ttk.Label(content_frame)
    info_frame = ttk.Frame(content_frame, borderwidth=1, relief='solid')
    info_var = StringVar()
    # Long format lists and live output need scrolling, so the info panel is a
    # Text widget (not a Label) with a vertical Scrollbar. It's kept read-only
    # (state='disabled') and synced from info_var via a trace (_sync_info_text)
    # so all existing info_var.set(...) call sites keep working unchanged.
    info_text = Text(info_frame, width=40, height=10, wrap='word',
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
    format_frame.grid(column=2, row=2, columnspan=3, sticky=W)
    format_combo.grid(column=0, row=0, padx=(0, 5))
    quality_combo.grid(column=1, row=0, padx=5)
    container_combo.grid(column=2, row=0, padx=5)
    size_label.grid(column=3, row=0, padx=(10, 0))
    options_frame.grid(column=2, row=3, columnspan=3, sticky=W)
    subs_check.grid(column=0, row=0, padx=(0, 5))
    subs_combo.grid(column=1, row=0, padx=5)
    all_formats_btn.grid(column=2, row=0, padx=(15, 5))
    custom_label.grid(column=3, row=0, padx=5)
    custom_clear_btn.grid(column=4, row=0)
    output_dir_label.grid(column=1, row=4, sticky=E)
    output_dir_value.grid(column=2, row=4, sticky=(W, E))
    browse_btn.grid(column=3, row=4, columnspan=2, sticky=W)
    cookie_options_frame.grid(column=1, row=5, columnspan=4, sticky=W)
    cookie_browser_check.grid(column=0, row=0, sticky=W)
    ttk.Label(cookie_options_frame, text="Browser:").grid(column=1, row=0, sticky=E)
    cookie_browser_combo.grid(column=2, row=0, sticky=W)
    cookie_file_label.grid(column=0, row=1, columnspan=4, sticky=W)
    content_frame.grid(column=1, row=6, columnspan=4, sticky=(N, W, E, S))
    thumb_label.grid(column=0, row=0, sticky=N, padx=(0, 8))
    info_frame.grid(column=1, row=0, sticky=(N, W, E, S))
    info_text.grid(column=0, row=0, sticky=(N, W, E, S))
    info_scroll.grid(column=1, row=0, sticky=(N, S))

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(2, weight=2)
    frame.rowconfigure(6, weight=2)
    content_frame.columnconfigure(1, weight=1)
    content_frame.rowconfigure(0, weight=1)
    info_frame.columnconfigure(0, weight=1)
    info_frame.rowconfigure(0, weight=1)

    # Apply uniform padding BEFORE hiding widgets below: grid_configure() on a
    # grid_remove()d widget re-maps it, so padding must be set while everything
    # is still gridded, then the initially-hidden widgets removed afterwards.
    for child in frame.winfo_children():
        child.grid(padx=5, pady=5)

    # The format controls start hidden; they appear after a successful check.
    format_label.grid_remove()
    format_frame.grid_remove()
    options_frame.grid_remove()
    custom_label.grid_remove()
    custom_clear_btn.grid_remove()
    # Thumbnail starts hidden; it appears after a successful check.
    thumb_label.grid_remove()
    # The Stop button starts hidden; it appears only during a download.
    stop_btn.grid_remove()

    update_cookie_controls()
    update_cookie_file_label()
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
