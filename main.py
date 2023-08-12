# URL to check:
# https://www.youtube.com/watch?v=dQw4w9WgXcQ

from tkinter import *
from tkinter import ttk
import subprocess

current_state = 'init'

def on_go(*args):
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
            go_title_var.set("download")
        else:
            go_title_var.set("check")


root = Tk()
root.title("YTDL")

mainframe = ttk.Frame(root, padding="3 3 12 12")
mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

url_var = StringVar()
url_entry = ttk.Entry(mainframe, width=7, textvariable=url_var)
url_entry.grid(column=2, row=1, sticky=(W, E))

info_var = StringVar()
ttk.Label(mainframe, textvariable=info_var).grid(column=2, row=2, sticky=(W, E))

go_title_var = StringVar(value="check")
go_btn = ttk.Button(mainframe, textvariable=go_title_var, command=on_go)
go_btn.grid(column=3, row=1, sticky=W)

ttk.Label(mainframe, text="URL:").grid(column=1, row=1, sticky=E)

for child in mainframe.winfo_children(): 
    child.grid_configure(padx=5, pady=5)

url_entry.focus()
root.bind("<Return>", on_go)

root.mainloop()