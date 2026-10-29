"""Compact single-window desktop workspace, shared hints and fleet controls."""
import tkinter as tk
from tkinter import ttk

from .map_canvas import MapCanvas, color_for, label_for
from .route_minimap import RouteMiniMap


class Hint:
    def __init__(self, widget, text):
        self.widget, self.text, self.popup, self.timer = widget, text, None, None
        widget.bind('<Enter>', self.schedule, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')
        widget.bind('<Destroy>', self.hide, add='+')

    def schedule(self, _=None):
        self.hide()
        self.timer = self.widget.after(450, self.show)

    def show(self):
        self.timer = None
        if not self.widget.winfo_exists():
            return
        text = self.text() if callable(self.text) else self.text
        if not text:
            return
        self.popup = tk.Toplevel(self.widget)
        self.popup.wm_overrideredirect(True)
        label = tk.Label(self.popup, text=text, background='#142235', foreground='#f1f5f9',
                 font=('Segoe UI', 9), padx=10, pady=7, wraplength=360, justify='left')
        label.pack()
        owner = self.widget.winfo_toplevel()
        x = min(self.widget.winfo_rootx()+8, owner.winfo_rootx()+owner.winfo_width()-label.winfo_reqwidth()-8)
        y = min(self.widget.winfo_rooty()+self.widget.winfo_height()+7,
                owner.winfo_rooty()+owner.winfo_height()-label.winfo_reqheight()-8)
        self.popup.wm_geometry(f'+{max(owner.winfo_rootx()+8,x)}+{max(owner.winfo_rooty()+8,y)}')

    def hide(self, _=None):
        if self.timer:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.popup:
            self.popup.destroy()
            self.popup = None


def icon(parent, glyph, command, hint, width=3):
    button = ttk.Button(parent, text=glyph, width=width, command=command, style='Icon.TButton')
    button.pack(side='left', padx=2)
    Hint(button, hint)
    return button


def build_workspace(app):
    from .map_launcher import GROUPS, INCIDENTS
    root = app.root
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Segoe UI', 9), background='#edf2f7', foreground='#21334b')
    style.configure('TButton', padding=(6, 4), borderwidth=0)
    style.configure('Icon.TButton', padding=(4, 4), font=('Segoe UI', 11))
    style.configure('TNotebook', borderwidth=0)
    style.configure('TNotebook.Tab', padding=(9, 5), background='#e2e8f0', foreground='#64748b')
    style.map('TNotebook.Tab', background=[('selected','#ffffff')], foreground=[('selected','#2563eb')])
    style.map('TButton', background=[('active','#dbeafe')])
    style.configure('TEntry', fieldbackground='#ffffff', bordercolor='#dbe3ed')
    style.configure('TCombobox', fieldbackground='#ffffff', bordercolor='#dbe3ed')
    style.configure('TCombobox', padding=2)
    style.configure('Title.TLabel', font=('Segoe UI', 15, 'bold'))
    root.configure(background='#edf2f7')
    root.title('AliveMap · Simulation workspace')
    root.geometry(f'{min(1440, root.winfo_screenwidth()-70)}x{min(900, root.winfo_screenheight()-100)}+20+20')
    root.minsize(1000, 650)
    outer = ttk.Frame(root, padding=8); outer.pack(fill='both', expand=True)
    header = ttk.Frame(outer); header.pack(fill='x', pady=(0, 7))
    ttk.Label(header, text='AliveMap', style='Title.TLabel').pack(side='left')
    ttk.Label(header, text='  /  SIMULATION WORKSPACE', foreground='#64748b').pack(side='left')
    app.connection_led = tk.Button(header, text='● MEC', foreground='#94a3b8', background='#edf2f7',
        activebackground='#dbeafe', relief='flat', borderwidth=0, cursor='hand2', command=lambda: app.send('refresh'))
    app.connection_led.pack(side='right', padx=7)
    Hint(app.connection_led, lambda: app.connection_hint())
    icon(header, '⚙', app.show_settings, 'Settings and connection details')
    ttk.Label(header, textvariable=app.clock, font=('Consolas', 10)).pack(side='right', padx=15)

    vertical = ttk.Panedwindow(outer, orient='vertical'); vertical.pack(fill='both', expand=True)
    upper = ttk.Panedwindow(vertical, orient='horizontal')
    vertical.add(upper, weight=4)
    app.inspector = ttk.Frame(upper, width=290)
    upper.add(app.inspector, weight=0)
    app.map_host = ttk.Frame(upper)
    upper.add(app.map_host, weight=1)
    app.canvas = MapCanvas(app.map_host, status=app.tile_status.set)
    app.canvas.pack(fill='both', expand=True)
    app.canvas.on_vehicle_select = app.select_fleet_vehicle
    app.minimap = RouteMiniMap(app.canvas)
    app.minimap.place(x=12, rely=1, y=-62, anchor='sw', width=270, height=175)
    Hint(app.minimap, 'Real road network: solid = current route, dashed = abandoned section. Double-click to expand.')
    app.fleet_panel = ttk.Frame(app.map_host, padding=4)
    app.fleet_panel.place(relx=1, x=-12, y=12, anchor='ne')
    app.fleet_signature = None
    app.fleet_expanded = False
    app.render_fleet()
    map_tools = ttk.Frame(app.map_host, padding=3)
    map_tools.place(relx=1, rely=1, x=-12, y=-37, anchor='se')
    icon(map_tools, '+', lambda: app.canvas.change_zoom(1), 'Zoom in')
    icon(map_tools, '−', lambda: app.canvas.change_zoom(-1), 'Zoom out')
    icon(map_tools, '⌖', app.overview, 'Show all vehicles and routes')
    icon(map_tools, '▧', lambda: app.toggle_minimap(), 'Show or hide route overview')


    bottom = ttk.Frame(vertical, height=235); vertical.add(bottom, weight=1)
    transport = ttk.Frame(bottom, padding=(0, 5)); transport.pack(fill='x')
    icon(transport, '↺', lambda: app.send('reset'), 'Restart from the scene’s initial state. This clears this run’s incidents; it is not reverse playback.')
    app.play_button = icon(transport, '▶', app.toggle_play, 'Play / pause • Space')
    icon(transport, '▸|', lambda: app.send('step'), 'Advance one simulation step • Right arrow')
    icon(transport, '»', app.faster, 'Increase target playback speed')
    speed = ttk.Combobox(transport, textvariable=app.speed, values=['1x','2x','5x','10x','20x','50x','100x'], state='readonly', width=6)
    speed.pack(side='left', padx=5); speed.bind('<<ComboboxSelected>>', lambda e: app.set_speed())
    Hint(speed, 'Target simulation seconds per real second. Actual rate is shown in Status.')
    app.timeline = tk.Canvas(transport, height=26, background='#edf2f7', highlightthickness=0)
    app.timeline.pack(side='left', fill='x', expand=True, padx=12)
    Hint(app.timeline, 'Elapsed simulation timeline; markers show route changes. Live simulation cannot seek backwards. Use restart to replay.')
    ttk.Checkbutton(transport, text='Inspect reroutes', variable=app.pause_on_change,
        command=lambda: app.worker.commands.put(('review_mode', app.pause_on_change.get()))).pack(side='right')
    Hint(transport.winfo_children()[-1], 'Pause automatically after a routing decision so you can inspect the changed route.')

    details = ttk.Frame(bottom); details.pack(fill='both',expand=True)
    config = ttk.Frame(details, width=280, padding=(5, 5, 12, 5)); config.pack(side='left', fill='y')
    ttk.Label(config, text='SCENARIO', foreground='#64748b').pack(anchor='w')
    app.map_box = app.combo(config, 'Map', app.map, list(GROUPS))
    app.region_box = app.combo(config, 'Subregion', app.region, [])
    app.scenario_box = ttk.Combobox(config, textvariable=app.scenario, state='readonly')
    app.combo(config, 'Incident', app.incident, list(INCIDENTS))
    app.map_box.bind('<<ComboboxSelected>>', lambda e: app.select_map())
    app.region_box.bind('<<ComboboxSelected>>', lambda e: app.select_region())
    row = ttk.Frame(config); row.pack(fill='x', pady=4)
    icon(row, '▷', lambda: app.load('none'), 'Run seeded trips without an incident')
    icon(row, '⚑', app.load, 'Run seeded trips with the selected incident at 20 simulated seconds')
    icon(row, '□', lambda: app.editor.open_scene(False), 'Create an empty editable playground')
    icon(row, '✦', lambda: app.editor.open_scene(True), 'Load the selected map’s editable demonstration, paused')
    app.diagnostics = ttk.Notebook(details); app.diagnostics.pack(side='left', fill='both', expand=True, padx=(5,0))
    logs, status, state, settings = [ttk.Frame(app.diagnostics, padding=6) for _ in range(4)]
    for page, name in zip((logs,status,state,settings), ('Logs','Status','Current state','Settings')):
        app.diagnostics.add(page, text=name)
    app.settings_page = settings
    app.history = tk.Text(logs, height=6, wrap='word', font=('Consolas', 9), background='#142235', foreground='#d6e3f3', relief='flat', state='disabled')
    scroll = ttk.Scrollbar(logs, command=app.history.yview); scroll.pack(side='right', fill='y')
    app.history.configure(yscrollcommand=scroll.set); app.history.pack(fill='both', expand=True)
    for variable in (app.status, app.comparison, app.story):
        ttk.Label(status, textvariable=variable, wraplength=800).pack(anchor='w', pady=4)
    ttk.Label(state, textvariable=app.vehicle_detail, wraplength=800).pack(anchor='w')
    app.profile = tk.Canvas(state, height=85, background='#f7fafc', highlightthickness=0); app.profile.pack(fill='both', expand=True)
    app.combo(settings, 'MEC', app.mode, ['Local demo (no SSH)','Physical MEC (HTTPS / SSH)'])
    app.combo(settings, 'Map layer', app.layer, list(app.canvas.sources)).bind('<<ComboboxSelected>>', lambda e: app.canvas.set_source(app.layer.get()))
    ttk.Checkbutton(settings, text='Open native SUMO window on next load', variable=app.sumo_gui).pack(anchor='w')
    ttk.Label(settings, text='Backend changes apply on the next scene load. Tower coverage is simulated.', foreground='#64748b').pack(anchor='w', pady=4)
    footer = ttk.Frame(outer); footer.pack(fill='x')
    ttk.Label(footer, textvariable=app.tile_status, foreground='#64748b').pack(side='left')
    root.bind('<space>', app.keyboard_play)
    root.bind('<Right>', app.keyboard_step)
    app._layout_ready = False
    def arrange(_=None):
        if not app._layout_ready and vertical.winfo_height() > 350 and upper.winfo_width() > 600:
            app._layout_ready = True
            upper.sashpos(0, 290)
            vertical.sashpos(0, max(280, vertical.winfo_height()-235))
    vertical.bind('<Configure>', lambda e: root.after_idle(arrange), add='+')
    root.after(250, arrange)
