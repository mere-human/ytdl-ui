# URL to check:
# https://www.youtube.com/watch?v=dQw4w9WgXcQ

from tkinter import *
from tkinter import ttk
import subprocess
import threading

current_state = 'init'

YT_DLP_NOT_FOUND = (
    'Error: yt-dlp not found. Install it with:\n'
    '  pip install -r requirements.txt\n'
    'or visit https://github.com/yt-dlp/yt-dlp#installation'
)


def run_download(*args):
    """Run yt-dlp and return the CompletedProcess, or None if not found."""
    try:
        return subprocess.run(
            ["yt-dlp", *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return None


def run_download_live(*args, on_line=None):
    """Run yt-dlp with live line-by-line output via on_line callback.

    Returns (returncode, stderr) or None if yt-dlp not found.
    """
    try:
        proc = subprocess.Popen(
            ["yt-dlp", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return None

    # Stream stdout line by line
    for line in proc.stdout:
        if on_line:
            on_line(line)

    proc.wait()
    stderr = proc.stderr.read()
    proc.stderr.close()
    proc.stdout.close()
    return proc.returncode, stderr


def set_busy(busy):
    """Disable/enable the button and entry during background work."""
    state = 'disabled' if busy else 'normal'
    run_btn.configure(state=state)
    url_entry.configure(state=state)


def on_check_complete(ret):
    """Called on main thread when check finishes."""
    global current_state
    if ret is None:
        info_var.set(YT_DLP_NOT_FOUND)
        current_state = 'init'
    elif ret.returncode != 0:
        info_var.set(ret.stderr if ret.stderr else f'Unknown error: {ret.returncode}')
        current_state = 'init'
    else:
        info_var.set(ret.stdout)
        run_btn_var.set("download")
    set_busy(False)


def on_download_complete(returncode, stderr):
    """Called on main thread when download finishes."""
    global current_state
    if returncode != 0:
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
        ret = run_download("-F", url)
        root.after(0, on_check_complete, ret)
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


def run_download_in_thread(url):
    """Run download in background with live output; post result to main thread."""
    def worker():
        def on_line(line):
            # Schedule UI update on main thread with latest line
            root.after(0, lambda l=line: info_var.set(l.rstrip('\n')))

        result = run_download_live(url, on_line=on_line)
        if result is None:
            root.after(0, lambda: (
                info_var.set(YT_DLP_NOT_FOUND),
                set_busy(False),
            ))
        else:
            returncode, stderr = result
            root.after(0, on_download_complete, returncode, stderr)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


def run_btn_press(*args):
    global current_state
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

url_entry.focus()
root.bind("<Return>", run_btn_press)

root.mainloop()
