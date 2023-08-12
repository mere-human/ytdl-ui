from tkinter import *
from tkinter import ttk

def on_go(*args):
        pass

root = Tk()
root.title("YTDL")

mainframe = ttk.Frame(root, padding="3 3 12 12")
mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

url_var = StringVar()
url_entry = ttk.Entry(mainframe, width=7, textvariable=url_var)
url_entry.grid(column=2, row=1, sticky=(W, E))

meters = StringVar()
ttk.Label(mainframe, textvariable=meters).grid(column=2, row=2, sticky=(W, E))

ttk.Button(mainframe, text="go", command=on_go).grid(column=3, row=1, sticky=W)

ttk.Label(mainframe, text="URL:").grid(column=1, row=1, sticky=E)

for child in mainframe.winfo_children(): 
    child.grid_configure(padx=5, pady=5)

url_entry.focus()
root.bind("<Return>", on_go)

root.mainloop()