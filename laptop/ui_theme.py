"""One restrained dark palette and spacing system for the desktop shell."""
from tkinter import ttk

BG = '#181818'
PANEL = '#1f1f1f'
EDITOR = '#181818'
FIELD = '#2a2a2a'
BORDER = '#343434'
FG = '#cccccc'
MUTED = '#858585'
ACCENT = '#4daafc'
GREEN = '#89d185'
AMBER = '#cca700'
RED = '#f48771'


def apply(root):
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=PANEL, foreground=FG, font=('Segoe UI', 9),
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, focuscolor=ACCENT)
    style.configure('TFrame', background=PANEL)
    style.configure('Editor.TFrame', background=EDITOR)
    style.configure('TLabel', background=PANEL, foreground=FG, padding=0)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Title.TLabel', font=('Segoe UI', 10, 'bold'))
    style.configure('TButton', padding=(5, 3), width=0, background=FIELD, borderwidth=0, anchor='center')
    style.map('TButton', background=[('active', '#383838'), ('pressed', '#454545')],
              foreground=[('disabled', '#666666')])
    style.configure('Icon.TButton', padding=(5, 4), background=PANEL, borderwidth=0)
    style.configure('Primary.TButton', background='#0e639c', foreground='#ffffff')
    style.map('Primary.TButton', background=[('active','#1177bb'),('pressed','#0e639c')])
    style.configure('TEntry', fieldbackground=FIELD, foreground=FG, padding=(4, 3),
                    insertcolor=FG, borderwidth=1)
    style.configure('TCombobox', fieldbackground=FIELD, background=FIELD, foreground=FG,
                    arrowcolor=FG, padding=(4, 2), borderwidth=1, arrowsize=12)
    style.map('TCombobox', fieldbackground=[('readonly',FIELD),('disabled',PANEL)],
              foreground=[('readonly',FG),('disabled',MUTED)], selectbackground=[('readonly',FIELD)],
              selectforeground=[('readonly',FG)], background=[('active','#383838')])
    style.configure('TNotebook', background=PANEL, borderwidth=0, tabmargins=0)
    style.configure('TNotebook.Tab', background=PANEL, foreground=MUTED, padding=(8, 5),
                    borderwidth=0, focuscolor=PANEL, lightcolor=PANEL, darkcolor=PANEL, bordercolor=PANEL)
    style.map('TNotebook.Tab', background=[('selected',BG),('active','#292929')],
              foreground=[('selected','#ffffff'),('active',FG)], lightcolor=[('selected',PANEL)], darkcolor=[('selected',PANEL)], bordercolor=[('selected',PANEL)])
    style.configure('TCheckbutton', padding=0, background=PANEL, foreground=FG,
                    indicatorbackground=FIELD, indicatorforeground=ACCENT)
    style.map('TCheckbutton', background=[('active',PANEL)])
    style.configure('TPanedwindow', background=BORDER, sashwidth=3)
    style.configure('TSeparator', background=BORDER)
    style.configure('Vertical.TScrollbar', background='#424242', troughcolor=PANEL,
                    borderwidth=0, arrowsize=10, width=10)
    style.configure('Horizontal.TScrollbar', background='#424242', troughcolor=PANEL,
                    borderwidth=0, arrowsize=10, width=10)
    for direction in ('Vertical','Horizontal'):
        name=direction+'.TScrollbar'
        style.configure(name,arrowcolor=MUTED,lightcolor='#424242',darkcolor='#424242',bordercolor=PANEL)
        style.map(name,background=[('active','#666666'),('pressed','#777777')],
                  lightcolor=[('active','#666666')],darkcolor=[('active','#666666')])
        axis='ns' if direction=='Vertical' else 'ew'
        style.layout(name,[(direction+'.Scrollbar.trough',{'sticky':axis,
            'children':[(direction+'.Scrollbar.thumb',{'expand':1,'sticky':'nswe'})]})])
    root.configure(background=BG)
    root.option_add('*TCombobox*Listbox.background', FIELD)
    root.option_add('*TCombobox*Listbox.foreground', FG)
    root.option_add('*TCombobox*Listbox.selectBackground', '#094771')
    root.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
    root.option_add('*TCombobox*Listbox.font', ('Segoe UI',9))
    return style
