# URL to check:
# https://www.youtube.com/watch?v=dQw4w9WgXcQ

from tkinter import *
from tkinter import ttk
import subprocess

current_state = 'init'

def run_btn_press(*args):
    global current_state
    if current_state == 'init':
        info_var.set('Getting info...')
        current_state = 'info'
        ret = subprocess.run(["youtube-dl", "-F", url_var.get()], capture_output=True)
    elif current_state == 'info':
        info_var.set('Downloading...')
        current_state = 'download'
        # ret = subprocess.run(["youtube-dl", url_var.get()], capture_output=True)
        ret = subprocess.run(["youtube-dl", '--help'], capture_output=True)
        current_state = 'init'

    if ret.returncode != 0:
        info_var.set(ret.stderr if ret.stderr else f'Unknown error: {ret.returncode}')
        current_state = 'init'
    else:
        info_var.set(ret.stdout)
        if current_state == 'info':
            run_btn_var.set("download")
        else:
            run_btn_var.set("check")


root = Tk()
root.title("YTDL")

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